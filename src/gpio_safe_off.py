#!/usr/bin/env python3
"""
Force both valve relays OFF.

Run by systemd as ExecStopPost of strop-api, i.e. after every stop, crash or
watchdog kill, so a valve can never stay open while the service is down.
Safe to run by hand. Does nothing when RPi.GPIO is unavailable.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


def main() -> int:
    try:
        from src.services.config_service import ConfigService
        gpio_cfg = ConfigService().get('gpio', {}) or {}
    except Exception:
        gpio_cfg = {}
    pins = [gpio_cfg.get('valve1_pin', 23), gpio_cfg.get('valve2_pin', 24)]
    try:
        import RPi.GPIO as GPIO
    except ImportError:
        print("RPi.GPIO not available, nothing to do")
        return 0
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    for pin in pins:
        # keep the pin as an OUTPUT driven LOW (no GPIO.cleanup, which would
        # leave it floating as an input)
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
        GPIO.output(pin, GPIO.LOW)
    print(f"Valve relays forced OFF (GPIO {', '.join(map(str, pins))})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
