#!/usr/bin/env python3
"""
Animatronic Eye Face Tracker
Uses OpenCV to detect a face and drives 3D-printed eyes via 5–6 PCA9685-connected
servo motors, matching the servo configuration defined in bechele/ConfigL.pm.

Hardware:
  Raspberry Pi + Logitech USB camera + PCA9685 PWM board
  Servo channels (all 12-bit PWM, 0–4096 steps at 50 Hz):
    Ch 0  EyeRight left/right  start=203  end=390  normal
    Ch 1  EyeLeft  left/right  start=270  end=415  normal
    Ch 2  EyeRight up/down     start=211  end=578  inverted
    Ch 3  EyeLeft  up/down     start=208  end=530  inverted
    Ch 4  LidRight              start=248  end=531  inverted
    Ch 5  LidLeft               start=239  end=540  inverted

Dependencies (install on Raspberry Pi):
    pip install opencv-python adafruit-circuitpython-pca9685 adafruit-blinka

Optional UDP mode (--udp flag) broadcasts servo packets on port 7625 using the
bechele wire format so existing ESP32 network nodes can receive them instead of
the direct I2C path.
"""

import argparse
import struct
import socket
import threading
import time

import cv2
import numpy as np

# Adafruit PCA9685 — only available on Raspberry Pi with blinka installed
try:
    import board
    import busio
    from adafruit_pca9685 import PCA9685
    _HW_AVAILABLE = True
except ImportError:
    _HW_AVAILABLE = False

# gpiozero — for direct GPIO servo control (Pi only)
try:
    from gpiozero import Servo as _GpioServo
    _GPIO_AVAILABLE = True
except ImportError:
    _GPIO_AVAILABLE = False


# ---------------------------------------------------------------------------
# Servo configuration — values taken directly from bechele ConfigL.pm
# Format: channel → (pwm_start, pwm_end, inverted, label)
# ---------------------------------------------------------------------------
SERVO_CFG = {
    0: (203, 390, False, "EyeRight left/right"),
    1: (270, 415, False, "EyeLeft  left/right"),
    2: (211, 578, True,  "EyeRight up/down"),
    3: (208, 530, True,  "EyeLeft  up/down"),
    4: (248, 531, True,  "LidRight"),
    5: (239, 540, True,  "LidLeft"),
}

# GPIO pin assignments for direct servo control — BCM (Broadcom) numbering.
# Change these to match your physical wiring.
# GPIO 12/13/18/19 support hardware PWM; the rest use software PWM.
GPIO_PINS = {
    0: 12,   # EyeRight left/right
    1: 13,   # EyeLeft  left/right
    2: 18,   # EyeRight up/down
    3: 19,   # EyeLeft  up/down
    4: 24,   # LidRight
    5: 25,   # LidLeft
}

# Physical pulse widths for each servo channel in milliseconds.
# Standard hobby servo: min=1.0ms, max=2.0ms (neutral at 1.5ms).
# Wide-range servo:     min=0.5ms, max=2.5ms.
# The bechele PCA9685 counts in SERVO_CFG can exceed 2ms when converted,
# which causes standard servos to spin against their end-stop. Set these
# to the actual range your servos accept, then tune SERVO_CFG to map
# movement within that physical range.
GPIO_PULSE_MS = {
    0: (1.0, 2.0),   # EyeRight left/right
    1: (1.0, 2.0),   # EyeLeft  left/right
    2: (1.0, 2.0),   # EyeRight up/down
    3: (1.0, 2.0),   # EyeLeft  up/down
    4: (1.0, 2.0),   # LidRight
    5: (1.0, 2.0),   # LidLeft
}

# PCA9685 hardware settings
I2C_ADDRESS  = 0x40   # default address; next board is 0x41, etc.
PWM_FREQ_HZ  = 50     # must match bechele i2c_freq

# Camera
CAMERA_INDEX  = 0
FRAME_WIDTH   = 640
FRAME_HEIGHT  = 480

# Control loop
LOOP_HZ       = 20    # matches bechele's 20 Hz refresh rate
SMOOTHING     = 0.15  # low-pass coefficient (higher = faster response)
DEAD_ZONE     = 0.05  # normalised dead-zone radius around centre
SNAP_THRESHOLD = 0.002  # snap smoothed position to target when this close

# Blink
BLINK_INTERVAL_S = 5.0
BLINK_DURATION_S = 0.12

# Face lost — seconds before eyes drift back to centre
FACE_TIMEOUT_S = 2.0

# UDP (bechele wire format)
UDP_PORT      = 7625
UDP_BROADCAST = "255.255.255.255"
UDP_SLOTS     = 64    # bechele always sends 64 servo slots


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def norm_to_pwm(value: float, start: int, end: int, inverted: bool) -> int:
    """Map normalised position [-1, +1] → PWM count within [start, end].

    0.0 → midpoint.  Clamps to [start, end].
    """
    if inverted:
        value = -value
    mid  = (start + end) / 2.0
    half = (end - start) / 2.0
    return int(max(start, min(end, mid + value * half)))


def _crc16(data: bytes) -> int:
    """CRC-16/IBM as used in bechele UDP packets."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


# ---------------------------------------------------------------------------
# Hardware / output layer
# ---------------------------------------------------------------------------

class ServoDriver:
    """Abstracts GPIO, PCA9685 (I2C), and UDP output behind a common interface."""

    def __init__(self, use_udp: bool = False, use_gpio: bool = False):
        self._use_udp   = use_udp
        self._use_gpio  = use_gpio
        self._pca       = None
        self._sock      = None
        self._gpio_servos: dict[int, "_GpioServo"] = {}
        self._last_gpio_norm: dict[int, float] = {}
        self._counter   = 0

        if use_gpio:
            if not _GPIO_AVAILABLE:
                raise RuntimeError(
                    "gpiozero not installed. Run: pip install gpiozero lgpio"
                )
            for ch, pin in GPIO_PINS.items():
                min_ms, max_ms = GPIO_PULSE_MS[ch]
                self._gpio_servos[ch] = _GpioServo(
                    pin,
                    min_pulse_width=min_ms / 1000,
                    max_pulse_width=max_ms / 1000,
                )
            pins = ", ".join(f"ch{c}→GPIO{p}" for c, p in GPIO_PINS.items())
            print(f"[driver] GPIO direct — {pins}")
        elif use_udp:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            print(f"[driver] UDP → {UDP_BROADCAST}:{UDP_PORT}")
        elif _HW_AVAILABLE:
            try:
                i2c = busio.I2C(board.SCL, board.SDA)
                self._pca = PCA9685(i2c, address=I2C_ADDRESS)
                self._pca.frequency = PWM_FREQ_HZ
                print(f"[driver] PCA9685 I2C 0x{I2C_ADDRESS:02X} @ {PWM_FREQ_HZ} Hz")
            except Exception as exc:
                print(f"[driver] I2C init failed ({exc}); falling back to simulation mode")
        else:
            print("[driver] Simulation mode — no hardware detected (import failed)")

    def write(self, pwm_map: dict[int, int]) -> None:
        """Send {channel: pwm_value, …} to hardware."""
        if self._use_gpio:
            for ch, pwm_val in pwm_map.items():
                if ch not in self._gpio_servos:
                    continue
                s, e, inv, _ = SERVO_CFG[ch]
                mid  = (s + e) / 2.0
                half = (e - s) / 2.0
                norm = (pwm_val - mid) / half
                if inv:
                    norm = -norm
                norm = max(-1.0, min(1.0, norm))
                if abs(norm - self._last_gpio_norm.get(ch, float("inf"))) < 0.001:
                    continue
                self._last_gpio_norm[ch] = norm
                self._gpio_servos[ch].value = norm
        elif self._use_udp:
            self._send_udp(pwm_map)
        elif self._pca:
            for ch, val in pwm_map.items():
                # Adafruit duty_cycle is 16-bit; scale from 12-bit bechele value
                self._pca.channels[ch].duty_cycle = val * 65535 // 4096
        else:
            parts = "  ".join(f"ch{ch}={v}" for ch, v in sorted(pwm_map.items()))
            print(f"[sim] {parts}")

    def _send_udp(self, pwm_map: dict[int, int]) -> None:
        positions = [390] * UDP_SLOTS  # safe neutral value for unused channels
        for ch, val in pwm_map.items():
            if ch < UDP_SLOTS:
                positions[ch] = val

        self._counter = (self._counter + 1) & 0xFFFF
        header  = struct.pack(">HH", UDP_SLOTS * 2, self._counter)
        body    = struct.pack(f">{UDP_SLOTS}H", *positions)
        payload = header + body
        packet  = payload + struct.pack("<H", _crc16(payload))
        self._sock.sendto(packet, (UDP_BROADCAST, UDP_PORT))

    def close(self) -> None:
        for servo in self._gpio_servos.values():
            servo.detach()
        if self._pca:
            self._pca.deinit()
        if self._sock:
            self._sock.close()


# ---------------------------------------------------------------------------
# Eye controller — manages smoothed positions and lid state
# ---------------------------------------------------------------------------

class EyeController:
    def __init__(self, driver: ServoDriver):
        self._driver = driver

        # Smooth targets (updated each control loop tick)
        self.target_x  = 0.0   # -1=left, +1=right
        self.target_y  = 0.0   # -1=up,   +1=down
        self._curr_x   = 0.0
        self._curr_y   = 0.0

        # 0.0 = lids fully open, 1.0 = lids fully closed
        self.lid = 0.0

    def tick(self) -> None:
        """Apply smoothing and push positions to hardware.  Call at LOOP_HZ."""
        dx = self.target_x - self._curr_x
        self._curr_x = self.target_x if abs(dx) < SNAP_THRESHOLD else self._curr_x + dx * SMOOTHING
        dy = self.target_y - self._curr_y
        self._curr_y = self.target_y if abs(dy) < SNAP_THRESHOLD else self._curr_y + dy * SMOOTHING

        pwm_map: dict[int, int] = {}

        # Horizontal
        for ch in (0, 1):
            s, e, inv, _ = SERVO_CFG[ch]
            pwm_map[ch] = norm_to_pwm(self._curr_x, s, e, inv)

        # Vertical
        for ch in (2, 3):
            s, e, inv, _ = SERVO_CFG[ch]
            pwm_map[ch] = norm_to_pwm(self._curr_y, s, e, inv)

        # Lids: map [0,1] → [-1,+1] for norm_to_pwm
        lid_norm = self.lid * 2.0 - 1.0
        for ch in (4, 5):
            s, e, inv, _ = SERVO_CFG[ch]
            pwm_map[ch] = norm_to_pwm(lid_norm, s, e, inv)

        self._driver.write(pwm_map)

    def centre(self) -> None:
        self.target_x = 0.0
        self.target_y = 0.0

    def home(self) -> None:
        """Snap all axes to home position instantly, bypassing smoothing."""
        self.target_x = 0.0
        self.target_y = 0.0
        self._curr_x  = 0.0
        self._curr_y  = 0.0
        self.lid      = 0.0
        self.tick()


# ---------------------------------------------------------------------------
# Face detector
# ---------------------------------------------------------------------------

class FaceDetector:
    def __init__(self):
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._clf = cv2.CascadeClassifier(cascade_path)
        if self._clf.empty():
            raise RuntimeError(f"Cannot load Haar cascade: {cascade_path}")

    def detect(self, frame: np.ndarray):
        """Return (norm_x, norm_y, rect) for the largest face, or (None, None, None)."""
        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._clf.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=6, minSize=(60, 60)
        )
        if len(faces) == 0:
            return None, None, None

        x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
        cx = x + w / 2
        cy = y + h / 2

        fh, fw = frame.shape[:2]
        nx = (cx - fw / 2) / (fw / 2)
        ny = (cy - fh / 2) / (fh / 2)

        if abs(nx) < DEAD_ZONE:
            nx = 0.0
        if abs(ny) < DEAD_ZONE:
            ny = 0.0

        return nx, ny, (x, y, w, h)


# ---------------------------------------------------------------------------
# Preview overlay
# ---------------------------------------------------------------------------

def draw_overlay(frame: np.ndarray, rect, nx: float, ny: float) -> None:
    if rect is not None:
        x, y, w, h = rect
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.circle(frame, (x + w // 2, y + h // 2), 5, (0, 255, 0), -1)
        cv2.putText(frame, f"x:{nx:+.2f} y:{ny:+.2f}",
                    (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 0), 1)

    fh, fw = frame.shape[:2]
    mid_x, mid_y = fw // 2, fh // 2
    cv2.line(frame, (mid_x - 15, mid_y), (mid_x + 15, mid_y), (0, 0, 200), 1)
    cv2.line(frame, (mid_x, mid_y - 15), (mid_x, mid_y + 15), (0, 0, 200), 1)
    cv2.putText(frame, "Q = quit", (8, 18),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)


# ---------------------------------------------------------------------------
# Blink thread
# ---------------------------------------------------------------------------

def _blink_worker(eyes: EyeController, stop: threading.Event) -> None:
    while not stop.wait(BLINK_INTERVAL_S):
        eyes.lid = 1.0
        stop.wait(BLINK_DURATION_S)
        eyes.lid = 0.0


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run(use_udp: bool, use_gpio: bool, show_preview: bool) -> None:
    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera index {CAMERA_INDEX}")

    detector = FaceDetector()
    driver   = ServoDriver(use_udp=use_udp, use_gpio=use_gpio)
    eyes     = EyeController(driver)

    print("Homing servos...")
    eyes.home()
    time.sleep(1.0)
    print("Homing complete.")

    stop_evt    = threading.Event()
    blink_thread = threading.Thread(
        target=_blink_worker, args=(eyes, stop_evt), daemon=True
    )
    blink_thread.start()

    interval        = 1.0 / LOOP_HZ
    last_face_time  = time.monotonic()

    print(f"Running at {LOOP_HZ} Hz — {'UDP' if use_udp else 'I2C'} output. "
          f"{'Preview on.' if show_preview else 'Headless.'}")

    try:
        while True:
            t0 = time.monotonic()

            ok, frame = cap.read()
            if not ok:
                time.sleep(0.05)
                continue

            # Flip horizontally so the preview feels like a mirror and
            # negate norm_x so the eyes still track in the correct direction.
            display_frame = cv2.flip(frame, 1)
            nx, ny, rect  = detector.detect(display_frame)
            if nx is not None:
                nx = -nx  # undo the display flip for servo direction
                eyes.target_x = nx
                eyes.target_y = ny
                last_face_time = time.monotonic()
            elif time.monotonic() - last_face_time > FACE_TIMEOUT_S:
                eyes.centre()

            eyes.tick()

            if show_preview:
                draw_overlay(display_frame, rect, nx or 0.0, ny or 0.0)
                cv2.imshow("Eye Tracker", display_frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

            sleep_s = interval - (time.monotonic() - t0)
            if sleep_s > 0:
                time.sleep(sleep_s)

    finally:
        stop_evt.set()
        blink_thread.join(timeout=1.0)
        eyes.centre()
        eyes.tick()
        driver.close()
        cap.release()
        if show_preview:
            cv2.destroyAllWindows()
        print("Shutdown complete.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Animatronic eye tracker — OpenCV + PCA9685 / bechele UDP"
    )
    parser.add_argument(
        "--gpio",
        action="store_true",
        help="Drive servos directly from GPIO pins (see GPIO_PINS in this file) "
             "instead of a PCA9685 board. Requires gpiozero and lgpio.",
    )
    parser.add_argument(
        "--udp",
        action="store_true",
        help="Broadcast servo packets via UDP (port 7625) for bechele network nodes "
             "instead of direct I2C to the PCA9685.",
    )
    parser.add_argument(
        "--no-preview",
        action="store_true",
        help="Disable the camera preview window (useful for headless operation).",
    )
    args = parser.parse_args()

    run(use_udp=args.udp, use_gpio=args.gpio, show_preview=not args.no_preview)
