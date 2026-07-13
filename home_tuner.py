#!/usr/bin/env python3
"""
Interactive home-position tuner — run directly on the Pi.

Homes all servos, then lets you nudge each eye live with the keyboard and
save the result as the new home position (TRIM in main.py).

Controls:
    Left eye   (ch1 L/R, ch3 U/D) : Arrow keys
    Right eye  (ch0 L/R, ch2 U/D) : W A S D
    +  /  -                       : increase / decrease step size
    Enter                         : save current position as home, exit
    Q                             : quit without saving

Usage:
    python3 home_tuner.py
"""

import curses
import re
from pathlib import Path

from main import SERVO_CFG, TRIM, norm_to_pwm, ServoDriver, EyeController

MAIN_PY = Path(__file__).parent / "main.py"

STEP_DEFAULT = 3
STEP_MIN = 1
STEP_MAX = 20

# channel -> (decrease_key, increase_key) for the eye axes only; lids are
# left at whatever TRIM already has and are not adjustable here.
KEY_BINDINGS = {
    1: ("left_arrow", "right_arrow"),   # EyeLeft  left/right
    3: ("up_arrow",   "down_arrow"),    # EyeLeft  up/down
    0: ("a", "d"),                      # EyeRight left/right
    2: ("w", "s"),                      # EyeRight up/down
}


def _write_trim(new_trim: dict[int, int]) -> None:
    text = MAIN_PY.read_text()
    lines = "\n".join(f"    {ch}: {new_trim[ch]}," for ch in sorted(new_trim))
    replacement = f"TRIM = {{\n{lines}\n}}"
    updated = re.sub(r"TRIM = \{[^}]*\}", replacement, text, count=1)
    MAIN_PY.write_text(updated)


def _run(stdscr) -> dict[int, int] | None:
    curses.curs_set(0)
    stdscr.nodelay(False)
    stdscr.keypad(True)

    driver = ServoDriver(use_gpio=False, use_udp=False)
    eyes = EyeController(driver)
    eyes.home()

    offset = {ch: 0 for ch in KEY_BINDINGS}
    step = STEP_DEFAULT
    result: dict[int, int] | None = None

    def push(ch: int) -> None:
        s, e, inv, _ = SERVO_CFG[ch]
        driver.write({ch: norm_to_pwm(0.0, s, e, inv, TRIM[ch] + offset[ch])})

    def render() -> None:
        stdscr.erase()
        stdscr.addstr(0, 0, "Home position tuner — arrows = left eye, WASD = right eye")
        stdscr.addstr(1, 0, "+/- = step size, ENTER = save as home, Q = quit without saving")
        stdscr.addstr(3, 0, f"Step size: {step} counts")
        row = 5
        for ch, (dec, inc) in KEY_BINDINGS.items():
            _, _, _, label = SERVO_CFG[ch]
            stdscr.addstr(row, 0, f"ch{ch}  {label:<20} trim={TRIM[ch]:+4d}  offset={offset[ch]:+4d}  ({dec}/{inc})")
            row += 1
        stdscr.refresh()

    render()

    while True:
        key = stdscr.getch()

        if key in (10, 13, curses.KEY_ENTER):
            result = {ch: TRIM[ch] + offset.get(ch, 0) for ch in TRIM}
            break
        if key in (ord("q"), ord("Q")):
            break

        if key == curses.KEY_LEFT:
            offset[1] -= step
            push(1)
        elif key == curses.KEY_RIGHT:
            offset[1] += step
            push(1)
        elif key == curses.KEY_UP:
            offset[3] -= step
            push(3)
        elif key == curses.KEY_DOWN:
            offset[3] += step
            push(3)
        elif key in (ord("a"), ord("A")):
            offset[0] -= step
            push(0)
        elif key in (ord("d"), ord("D")):
            offset[0] += step
            push(0)
        elif key in (ord("w"), ord("W")):
            offset[2] -= step
            push(2)
        elif key in (ord("s"), ord("S")):
            offset[2] += step
            push(2)
        elif key in (ord("+"), ord("=")):
            step = min(STEP_MAX, step + 1)
        elif key in (ord("-"), ord("_")):
            step = max(STEP_MIN, step - 1)

        render()

    driver.close()
    return result


def main() -> None:
    new_trim = curses.wrapper(_run)

    if new_trim is None:
        print("Quit without saving. TRIM unchanged.")
        return

    _write_trim(new_trim)
    print("Saved new home position to main.py TRIM:")
    for ch in sorted(new_trim):
        print(f"  {ch}: {new_trim[ch]}")


if __name__ == "__main__":
    main()
