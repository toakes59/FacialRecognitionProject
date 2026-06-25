#!/usr/bin/env python3
"""
Servo diagnostic test — run directly on the Pi before using main.py.

Tests each GPIO servo pin independently using gpiozero defaults (1–2 ms pulse
width, 50 Hz). No face detection or bechele logic involved.

Usage:
    python3 servo_test.py           # test all servos in sequence
    python3 servo_test.py --pin 18  # test a single GPIO pin
    python3 servo_test.py --hold    # hold center on all pins (Ctrl+C to quit)
    python3 servo_test.py --home    # move all servos to home position and hold
"""

import argparse
import time

try:
    from gpiozero import Servo
    from gpiozero.exc import GPIOPinInUse
except ImportError:
    raise SystemExit("gpiozero is not installed. Run: pip install gpiozero lgpio")

# Maps channel label → (GPIO BCM pin, home value)
# Home value is a gpiozero Servo value in [-1, +1]:
#   0.0  = center (1.5 ms) — used for all eye position servos
#  -1.0  = minimum pulse (1.0 ms) — used for lid servos in the "open" state
# These must match what EyeController.home() commands via main.py.
SERVOS = {
    "EyeRight L/R  (ch0)": (12,  0.0),
    "EyeLeft  L/R  (ch1)": (13,  0.0),
    "EyeRight U/D  (ch2)": (18,  0.0),
    "EyeLeft  U/D  (ch3)": (19,  0.0),
    "LidRight      (ch4)": (24, -1.0),
    "LidLeft       (ch5)": (25, -1.0),
}

PAUSE = 1.5  # seconds to hold each position


def test_servo(label: str, pin: int) -> None:
    print(f"\n--- {label}  GPIO {pin} ---")
    try:
        s = Servo(pin)
    except GPIOPinInUse:
        print(f"  SKIP: GPIO {pin} already in use by another process")
        return
    except Exception as exc:
        print(f"  ERROR creating servo on GPIO {pin}: {exc}")
        return

    steps = [
        ("center (1.5 ms)", s.mid),
        ("min    (1.0 ms)", s.min),
        ("center (1.5 ms)", s.mid),
        ("max    (2.0 ms)", s.max),
        ("center (1.5 ms)", s.mid),
    ]

    for description, fn in steps:
        print(f"  {description}", end="", flush=True)
        fn()
        time.sleep(PAUSE)
        print("  ✓")

    s.detach()
    time.sleep(0.3)


def hold_center(pins: list[int]) -> None:
    servos = []
    for pin in pins:
        try:
            s = Servo(pin)
            s.mid()
            servos.append(s)
            print(f"GPIO {pin}: holding center (1.5 ms)")
        except Exception as exc:
            print(f"GPIO {pin}: ERROR — {exc}")

    print("\nPress Ctrl+C to release servos and exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for s in servos:
            s.detach()
        print("Servos released.")


def home_servos(entries: list[tuple[str, int, float]]) -> None:
    """Move each servo to its home position and hold until Ctrl+C.

    Home positions match what EyeController.home() commands on startup:
      - Eye servos  → center (0.0)
      - Lid servos  → fully open (-1.0)

    Attach the servo horns/arms while servos are held at these positions.
    """
    servos = []
    for label, pin, home_val in entries:
        try:
            s = Servo(pin)
            s.value = home_val
            servos.append(s)
            pos = "center" if home_val == 0.0 else ("min/open" if home_val == -1.0 else f"{home_val:+.2f}")
            print(f"GPIO {pin:2d}  {label}: {pos}")
        except GPIOPinInUse:
            print(f"GPIO {pin}: SKIP — already in use")
        except Exception as exc:
            print(f"GPIO {pin}: ERROR — {exc}")

    print("\nServos are at home position. Attach horns/arms now.")
    print("Press Ctrl+C when done to release servos.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for s in servos:
            s.detach()
        print("Servos released.")


def main() -> None:
    parser = argparse.ArgumentParser(description="gpiozero servo diagnostic")
    parser.add_argument(
        "--pin",
        type=int,
        help="Test only this GPIO BCM pin instead of all servos",
    )
    parser.add_argument(
        "--hold",
        action="store_true",
        help="Hold all servos at center position (Ctrl+C to quit)",
    )
    parser.add_argument(
        "--home",
        action="store_true",
        help="Move all servos to home position and hold — use this when "
             "attaching servo horns to the 3D-printed eye assembly",
    )
    args = parser.parse_args()

    all_entries = [(lbl, pin, val) for lbl, (pin, val) in SERVOS.items()]

    if args.home:
        entries = (
            [(lbl, pin, val) for lbl, (pin, val) in SERVOS.items() if pin == args.pin]
            if args.pin else all_entries
        )
        home_servos(entries)
        return

    if args.hold:
        pins = [args.pin] if args.pin else [pin for _, (pin, _) in SERVOS.items()]
        hold_center(pins)
        return

    if args.pin:
        label = next(
            (lbl for lbl, (p, _) in SERVOS.items() if p == args.pin),
            f"GPIO {args.pin}",
        )
        test_servo(label, args.pin)
    else:
        print("Testing all servos with standard 1–2 ms pulse range.")
        print("Each servo will move: center → min → center → max → center")
        print(f"Holding each position for {PAUSE}s.\n")
        for label, (pin, _) in SERVOS.items():
            test_servo(label, pin)

    print("\nDone. If any servo spun continuously instead of moving to a position,")
    print("the issue is in gpiozero or the Pi 5 PWM backend — not the pulse widths.")


if __name__ == "__main__":
    main()
