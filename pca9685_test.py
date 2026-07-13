#!/usr/bin/env python3
"""
PCA9685 servo diagnostic test — run directly on the Pi before using main.py.

Mirrors servo_test.py but drives the PCA9685 I2C board instead of direct
GPIO pins. Reuses SERVO_CFG, norm_to_pwm, ServoDriver, and EyeController
from main.py so channel mapping, inversion, and home position always match
what main.py actually does at runtime.

Usage:
    python3 pca9685_test.py              # test all channels in sequence
    python3 pca9685_test.py --channel 2  # test a single PCA9685 channel
    python3 pca9685_test.py --hold       # hold center on all channels (Ctrl+C to quit)
    python3 pca9685_test.py --home       # move to home position and hold (attach horns)
"""

import argparse
import time

from main import SERVO_CFG, TRIM, norm_to_pwm, ServoDriver, EyeController

PAUSE = 1.5  # seconds to hold each position


def test_channel(driver: ServoDriver, channel: int, label: str, s: int, e: int, inv: bool) -> None:
    trim = TRIM[channel]
    print(f"\n--- {label}  ch{channel} ---")
    steps = [
        ("center (0.0)", 0.0),
        ("min    (-1.0)", -1.0),
        ("center (0.0)", 0.0),
        ("max    (+1.0)", 1.0),
        ("center (0.0)", 0.0),
    ]
    for description, norm in steps:
        print(f"  {description}", end="", flush=True)
        driver.write({channel: norm_to_pwm(norm, s, e, inv, trim)})
        time.sleep(PAUSE)
        print("  done")


def hold_center(driver: ServoDriver, channels: list[int]) -> None:
    for ch in channels:
        s, e, inv, label = SERVO_CFG[ch]
        driver.write({ch: norm_to_pwm(0.0, s, e, inv, TRIM[ch])})
        print(f"ch{ch}: holding center — {label}")

    print("\nPress Ctrl+C to release and exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


def home_and_hold(driver: ServoDriver) -> None:
    """Move all channels to the same home position main.py commands on startup
    (eyes centered, lids open) and hold until Ctrl+C — use this when attaching
    servo horns to the 3D-printed eye assembly.
    """
    eyes = EyeController(driver)
    eyes.home()
    for ch, (_, _, _, label) in SERVO_CFG.items():
        print(f"ch{ch}  {label}: home")

    print("\nChannels are at home position. Attach horns/arms now.")
    print("Press Ctrl+C when done to release.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="PCA9685 servo diagnostic")
    parser.add_argument(
        "--channel", type=int,
        help="Test only this PCA9685 channel instead of all",
    )
    parser.add_argument(
        "--hold", action="store_true",
        help="Hold all channels at center position (Ctrl+C to quit)",
    )
    parser.add_argument(
        "--home", action="store_true",
        help="Move to home position (eyes centered, lids open) and hold — "
             "use this when attaching servo horns to the eye assembly",
    )
    args = parser.parse_args()

    driver = ServoDriver(use_udp=False, use_gpio=False)

    try:
        if args.home:
            home_and_hold(driver)
            return

        if args.hold:
            channels = [args.channel] if args.channel is not None else list(SERVO_CFG.keys())
            hold_center(driver, channels)
            return

        if args.channel is not None:
            s, e, inv, label = SERVO_CFG[args.channel]
            test_channel(driver, args.channel, label, s, e, inv)
        else:
            print("Testing all channels: center -> min -> center -> max -> center")
            print(f"Holding each position for {PAUSE}s.\n")
            for ch, (s, e, inv, label) in SERVO_CFG.items():
                test_channel(driver, ch, label, s, e, inv)

        print("\nDone.")
    finally:
        driver.close()


if __name__ == "__main__":
    main()
