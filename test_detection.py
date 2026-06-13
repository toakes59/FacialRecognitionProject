#!/usr/bin/env python3
"""
Face detection test — runs on any machine with a webcam.
No Raspberry Pi hardware required.

What you'll see:
  - Live webcam feed
  - Red box around the detected face
  - Animated eye pair (bottom-right) that tracks the face — matches what
    the servos would do on the Pi
  - Left-side panel showing the PWM value each servo channel would receive

Press Q to quit.
"""

import argparse
import sys

import cv2
import numpy as np

# Mirror of the servo config in main.py — keep in sync if you change ranges
SERVO_CFG = {
    0: (203, 390, False, "EyeRight L/R"),
    1: (270, 415, False, "EyeLeft  L/R"),
    2: (211, 578, True,  "EyeRight U/D"),
    3: (208, 530, True,  "EyeLeft  U/D"),
    4: (248, 531, True,  "LidRight"),
    5: (239, 540, True,  "LidLeft"),
}

SMOOTHING    = 0.15
DEAD_ZONE    = 0.05
FRAME_WIDTH  = 640
FRAME_HEIGHT = 480


def norm_to_pwm(value: float, start: int, end: int, inverted: bool) -> int:
    if inverted:
        value = -value
    mid  = (start + end) / 2.0
    half = (end - start) / 2.0
    return int(max(start, min(end, mid + value * half)))


def detect_face(clf, frame):
    gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    faces = clf.detectMultiScale(
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


def draw_eye_sim(frame, smooth_x: float, smooth_y: float) -> None:
    """Animated eye pair that mirrors what the animatronic eyes would do."""
    fh, fw = frame.shape[:2]

    eye_r      = 32   # eyeball radius
    pupil_r    = 11   # pupil radius
    max_travel = 16   # max pixel offset for the pupil

    spacing  = 78
    base_cx  = fw - spacing // 2 - 10
    left_cx  = base_cx - spacing // 2
    right_cx = base_cx + spacing // 2
    eye_cy   = fh - 55

    # Background panel
    cv2.rectangle(frame,
                  (left_cx - eye_r - 8, eye_cy - eye_r - 22),
                  (right_cx + eye_r + 8, eye_cy + eye_r + 8),
                  (30, 30, 30), -1)
    cv2.putText(frame, "Eye simulation",
                (left_cx - eye_r - 4, eye_cy - eye_r - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (160, 160, 160), 1)

    for cx in (left_cx, right_cx):
        cv2.circle(frame, (cx, eye_cy), eye_r, (240, 240, 240), -1)
        cv2.circle(frame, (cx, eye_cy), eye_r, (150, 150, 150), 1)
        px = int(cx  + smooth_x * max_travel)
        py = int(eye_cy + smooth_y * max_travel)
        # Clamp pupil inside sclera
        dx, dy = px - cx, py - eye_cy
        dist = (dx**2 + dy**2) ** 0.5
        limit = eye_r - pupil_r - 2
        if dist > limit:
            scale = limit / dist
            px = int(cx  + dx * scale)
            py = int(eye_cy + dy * scale)
        cv2.circle(frame, (px, py), pupil_r, (20, 20, 20), -1)
        cv2.circle(frame, (px - 3, py - 3), 3, (255, 255, 255), -1)  # glint


def draw_servo_panel(frame, smooth_x: float, smooth_y: float) -> None:
    """Left-side panel showing the PWM value each servo channel would receive."""
    panel_w = 200
    fh = frame.shape[0]
    cv2.rectangle(frame, (0, 0), (panel_w, fh), (20, 20, 20), -1)

    cv2.putText(frame, "Servo PWM targets", (6, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 200, 50), 1)
    cv2.line(frame, (6, 26), (panel_w - 6, 26), (80, 80, 80), 1)

    y = 46
    for ch, (s, e, inv, label) in SERVO_CFG.items():
        if ch in (0, 1):
            norm_val = smooth_x
        elif ch in (2, 3):
            norm_val = smooth_y
        else:
            norm_val = -1.0  # lids fully open

        pwm = norm_to_pwm(norm_val, s, e, inv)
        pct = (pwm - s) / (e - s)

        cv2.putText(frame, f"ch{ch} {label}", (6, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (180, 180, 180), 1)
        y += 14

        # Mini bar
        bar_x, bar_y, bar_h = 6, y - 10, 6
        bar_w = panel_w - 12
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_w, bar_y + bar_h),
                      (60, 60, 60), -1)
        filled = int(pct * bar_w)
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + filled, bar_y + bar_h),
                      (50, 180, 80), -1)
        cv2.putText(frame, str(pwm), (bar_x + bar_w + 2, bar_y + bar_h),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (140, 200, 140), 1)
        y += 18

    cv2.putText(frame, f"x:{smooth_x:+.2f}  y:{smooth_y:+.2f}",
                (6, fh - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (100, 180, 255), 1)


def main():
    parser = argparse.ArgumentParser(
        description="Face detection test — press Q to quit"
    )
    parser.add_argument("--camera", type=int, default=0,
                        help="Camera device index (default 0)")
    args = parser.parse_args()

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    clf = cv2.CascadeClassifier(cascade_path)
    if clf.empty():
        sys.exit(f"ERROR: could not load Haar cascade from {cascade_path}")

    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    if not cap.isOpened():
        sys.exit(f"ERROR: cannot open camera index {args.camera}")

    smooth_x = 0.0
    smooth_y = 0.0
    # Smoothed box position — gives the red box the same lag as the servos
    # so what you see on screen matches what the eyes will actually do
    box_x = box_y = box_w = box_h = 0.0

    print("Face detection test running — press Q in the window to quit.")

    while True:
        ok, frame = cap.read()
        if not ok:
            continue

        frame = cv2.flip(frame, 1)
        nx, ny, rect = detect_face(clf, frame)

        if nx is not None:
            nx = -nx  # undo mirror flip (same as main.py)
            smooth_x += (nx - smooth_x) * SMOOTHING
            smooth_y += (ny - smooth_y) * SMOOTHING
            rx, ry, rw, rh = rect
            box_x += (rx - box_x) * SMOOTHING
            box_y += (ry - box_y) * SMOOTHING
            box_w += (rw - box_w) * SMOOTHING
            box_h += (rh - box_h) * SMOOTHING

        # Red box — drawn at the smoothed position so it matches servo lag
        if box_w > 10:
            bx, by, bw, bh = int(box_x), int(box_y), int(box_w), int(box_h)
            cv2.rectangle(frame, (bx, by), (bx + bw, by + bh), (0, 0, 255), 2)
            cv2.circle(frame, (bx + bw // 2, by + bh // 2), 5, (0, 0, 255), -1)
            cv2.putText(frame, f"x:{smooth_x:+.2f}  y:{smooth_y:+.2f}",
                        (bx, by - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

        # Frame-centre crosshair
        fh, fw = frame.shape[:2]
        mcx, mcy = fw // 2, fh // 2
        cv2.line(frame, (mcx - 12, mcy), (mcx + 12, mcy), (80, 80, 200), 1)
        cv2.line(frame, (mcx, mcy - 12), (mcx, mcy + 12), (80, 80, 200), 1)

        draw_servo_panel(frame, smooth_x, smooth_y)
        draw_eye_sim(frame, smooth_x, smooth_y)

        cv2.putText(frame, "Q = quit", (fw - 72, 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 160), 1)

        cv2.imshow("Face Detection Test", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
