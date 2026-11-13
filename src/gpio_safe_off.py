#!/usr/bin/env python3
"""
Force all valve relays OFF.

Run by systemd as ExecStopPost of strop-api, i.e. after every stop, crash or
watchdog kill, so a valve can never stay open while the service is down.
Safe to run by hand. Does nothing when RPi.GPIO is unavailable.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


def collect_pins() -> list:
    """Pins of all configured zones. When the config is broken, every pin
    that can still be read from it (plus the defaults) is switched off: when
    in doubt, more relays OFF is the safe side."""
    from src.services.config_service import ConfigService, DEFAULT_ZONES, VALID_PINS, parse_zones
    try:
        config = ConfigService().get_all()
    except Exception:
        return sorted(DEFAULT_ZONES.values())
    try:
        return sorted(parse_zones(config).values())
    except Exception:
        pins = set(DEFAULT_ZONES.values())
        gpio = config.get('gpio') if isinstance(config.get('gpio'), dict) else {}
        candidates = [z.get('pin') for z in gpio.get('zones') or [] if isinstance(z, dict)]
        candidates += [v for k, v in gpio.items() if k.startswith('valve') and k.endswith('_pin')]
        for pin in candidates:
            try:
                if int(pin) in VALID_PINS:
                    pins.add(int(pin))
            except (TypeError, ValueError):
                pass
        return sorted(pins)


def main() -> int:
    pins = collect_pins()
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
