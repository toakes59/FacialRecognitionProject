#!/usr/bin/env python3
"""
Servo diagnostic test — run directly on the Pi before using main.py.

Tests each GPIO servo pin independently using gpiozero defaults (1–2 ms pulse
width, 50 Hz). No face detection or bechele logic involved.

Usage:
    python3 servo_test.py           # test all servos in sequence
    python3 servo_test.py --pin 18  # test a single GPIO pin
    python3 servo_test.py --hold    # hold center on all pins (Ctrl+C to quit)
"""

import argparse
import time

try:
    from gpiozero import Servo
    from gpiozero.exc import GPIOPinInUse
except ImportError:
    raise SystemExit("gpiozero is not installed. Run: pip install gpiozero lgpio")

# Maps channel label → GPIO BCM pin (must match GPIO_PINS in main.py)
SERVOS = {
    "EyeRight L/R  (ch0)": 12,
    "EyeLeft  L/R  (ch1)": 13,
    "EyeRight U/D  (ch2)": 18,
    "EyeLeft  U/D  (ch3)": 19,
    "LidRight      (ch4)": 24,
    "LidLeft       (ch5)": 25,
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
    args = parser.parse_args()

    if args.hold:
        pins = [args.pin] if args.pin else list(SERVOS.values())
        hold_center(pins)
        return

    if args.pin:
        label = next(
            (lbl for lbl, p in SERVOS.items() if p == args.pin),
            f"GPIO {args.pin}",
        )
        test_servo(label, args.pin)
    else:
        print("Testing all servos with standard 1–2 ms pulse range.")
        print("Each servo will move: center → min → center → max → center")
        print(f"Holding each position for {PAUSE}s.\n")
        for label, pin in SERVOS.items():
            test_servo(label, pin)

    print("\nDone. If any servo spun continuously instead of moving to a position,")
    print("the issue is in gpiozero or the Pi 5 PWM backend — not the pulse widths.")


if __name__ == "__main__":
    main()
