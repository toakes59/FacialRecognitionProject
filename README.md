# FacialRecognitionProject

Detects a person's face using OpenCV on a Raspberry Pi 5 and drives a set of 3D-printed animatronic eyes via servo motors so they follow the detected face in real time.

## How It Works

1. A USB camera (Logitech webcam) or Pi Camera feeds frames into OpenCV.
2. A Haar cascade classifier detects the largest face in the frame.
3. The face's center position is normalized to a [-1, +1] coordinate space.
4. A low-pass smoothing filter drives 6 servo channels on a PCA9685 PWM board, moving both eyeballs horizontally and vertically and controlling the eyelids.
5. A background thread triggers automatic blinking every 5 seconds.
6. If no face is detected for 2 seconds, the eyes drift back to center.

## Hardware

| Component | Notes |
|---|---|
| Raspberry Pi 5 | Primary compute board |
| Logitech USB webcam **or** Pi Camera | Camera index `0` by default |
| 6× servo motors | Signal wire to Pi GPIO pins (see table below) |
| 3D-printed animatronic eye assembly | See `bechele/` folder |

### GPIO Wiring (Direct Mode)

Connect each servo's **signal wire** to the GPIO pin listed below. Power and ground should go to a separate 5 V supply — do not power servos from the Pi's 3.3 V or 5 V pins.

| Servo | Function | Pi GPIO (BCM) | Pi Header Pin |
|---|---|---|---|
| EyeRight signal | Left / right | GPIO 12 | Pin 32 |
| EyeLeft signal | Left / right | GPIO 13 | Pin 33 |
| EyeRight signal | Up / down | GPIO 18 | Pin 12 |
| EyeLeft signal | Up / down | GPIO 19 | Pin 35 |
| LidRight signal | Open / close | GPIO 24 | Pin 18 |
| LidLeft signal | Open / close | GPIO 25 | Pin 22 |
| All servo GND | Common ground | GND | Pin 6 (or any GND) |

> GPIO 12, 13, 18, and 19 support **hardware PWM** on the Pi 5 and will give smoother servo movement. GPIO 24 and 25 use software PWM.

To change the pin assignments, edit the `GPIO_PINS` dict near the top of [main.py](main.py).

## Repository Layout

```
FacialRecognitionProject/
├── main.py                  # Primary entry point — run this on the Pi
├── test_detection.py        # Desktop test: webcam + face box + eye simulation
├── ComputerMQTT.py          # Alternative: publish face coords over MQTT
├── FaceRecognition.py       # Simple face-detection viewer (dev tool)
├── FacialRecognition.py     # Same as above (alternate copy)
├── MoveDemEyes.py           # GPIO-direct servo test with face detection
├── MQTTTest.py              # MQTT publisher test
├── PiMQTT.py                # MQTT subscriber for Pi-side servo control
├── ServoPi.py               # Servo min/mid/max test via gpiozero
├── servoController.py       # Same as ServoPi.py (alternate copy)
├── haarcascade_frontalface_default.xml  # OpenCV face cascade (bundled)
└── bechele/                 # Vendor software for the animatronic eye kit
```

The files other than `main.py` are earlier development iterations and utilities kept for reference.

## The `bechele/` Folder

This folder contains the Perl-based control software that ships with the 3D-printed animatronic eye files from [bechele.de](https://bechele.de). It is **not written by this project** — it is the vendor-provided tooling for the eye hardware.

Key tools inside:
- `trackui.pl` — interactive UI for recording eye movement sequences
- `live.pl` — plays back recorded sequences synchronized with audio
- `servocalib.pl` — servo calibration utility
- `nodeconfig.pl` — network node configuration for ESP32-based remote nodes

`main.py` is compatible with the bechele UDP wire format (port 7625) and uses the same servo PWM values defined in `bechele/usr/local/bin/bechele/Modules/ConfigL.pm`.

## Testing on Your Desktop (Before the Pi)

`test_detection.py` lets you verify the face detection and servo logic on any machine with a webcam — no Raspberry Pi hardware needed.

```bash
# Install the only dependency needed on a desktop
pip install opencv-python

# Run
python test_detection.py

# If your webcam isn't index 0
python test_detection.py --camera 1
```

What you'll see:

- **Red box** drawn around the detected face
- **Animated eye pair** (bottom-right corner) whose pupils track the face position exactly as the animatronic eyes would move on the Pi
- **Servo PWM panel** (left side) showing the 12-bit PWM value each servo channel would receive in real time, with a bar graph

If the face box and eye simulation track your face correctly here, the servo motion on the Pi will be correct too. Press **Q** to quit.

---

## Getting the Code onto the Pi

SSH into your Pi and clone this repository:

```bash
ssh pi@<your-pi-ip>
git clone https://github.com/<your-username>/FacialRecognitionProject.git
cd FacialRecognitionProject
```

## Installation

Run all of the following on the Pi after cloning.

```bash
# System packages (camera support, pip)
sudo apt update
sudo apt install -y python3-pip python3-opencv libcamera-apps

# Python dependencies for GPIO direct mode
pip3 install numpy gpiozero lgpio

# Optional: MQTT variant files only
pip3 install paho-mqtt
```

> `python3-opencv` installs OpenCV from the apt repository which is pre-built for the Pi. If you need a newer version you can instead use `pip3 install opencv-python`, but it takes much longer to build.

## Running

SSH into the Pi, navigate to the project folder, then run:

```bash
# GPIO direct mode — servos on the pins listed in the wiring table above
python3 main.py --gpio

# Headless (no monitor attached to the Pi)
python3 main.py --gpio --no-preview

# With camera preview visible on an attached monitor
python3 main.py --gpio
```

Press **Q** in the preview window to quit, or **Ctrl+C** in the terminal for headless mode.

### Other output modes (advanced)

```bash
# UDP mode — broadcasts bechele packets to ESP32 network nodes instead of GPIO
python3 main.py --udp --no-preview
```

## Tuning

Edit these constants near the top of `main.py`:

| Constant | Default | Effect |
|---|---|---|
| `CAMERA_INDEX` | `0` | Camera device index |
| `SMOOTHING` | `0.15` | Low-pass filter speed (higher = faster, jerkier) |
| `DEAD_ZONE` | `0.05` | Normalized dead zone around center (prevents jitter) |
| `LOOP_HZ` | `20` | Control loop rate |
| `BLINK_INTERVAL_S` | `5.0` | Seconds between automatic blinks |
| `BLINK_DURATION_S` | `0.12` | Duration of each blink |
| `FACE_TIMEOUT_S` | `2.0` | Seconds before eyes return to center when no face |

## Troubleshooting

### SSH disconnects immediately when running `python3 main.py`

OpenCV tries to open a GUI preview window, which kills the SSH session when no display is attached. Always pass `--no-preview` over SSH:

```bash
python3 main.py --gpio --no-preview
```

### `ValueError: No Hardware I2C on (scl,sda)=(3, 2)`

I2C is disabled on the Pi. Enable it and reboot:

```bash
sudo raspi-config
# Interface Options → I2C → Enable
sudo reboot
```

This only affects PCA9685 mode. If you are using direct GPIO wiring, pass `--gpio` and I2C is never used.

### Servos are not moving

Make sure you are passing the `--gpio` flag. Without it the script runs in simulation mode and only prints servo values to the terminal — no GPIO pins are driven:

```bash
python3 main.py --gpio --no-preview
```

### Some servos spin continuously in one direction

The bechele PCA9685 calibration values produce pulse widths up to ~2.8ms on some channels, which is outside the 1–2ms range standard hobby servos expect. A servo receiving a pulse beyond its physical range will spin against its end-stop.

Edit `GPIO_PULSE_MS` near the top of `main.py` to match your servos:

```python
# Standard hobby servo (SG90, MG90S, etc.)
GPIO_PULSE_MS = {
    0: (1.0, 2.0),
    1: (1.0, 2.0),
    ...
}

# Wide-range servo (some bechele-kit servos accept 0.5–2.5ms)
GPIO_PULSE_MS = {
    0: (0.5, 2.5),
    ...
}
```

Start with `(1.0, 2.0)` (the default). If the servo moves but hits its end-stop before reaching the extreme position, widen to `(0.5, 2.5)`.

---

## Requirements Summary

- Python 3.7+
- opencv-python (or `python3-opencv` via apt)
- numpy
- gpiozero
- lgpio (Pi 5 GPIO backend for gpiozero)
