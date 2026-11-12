#!/usr/bin/env python3
"""
Set (or change) the Strop controller password.

Run on the Pi from the project directory:

    venv/bin/python3 scripts/set_password.py

The password is stored only as a salted hash in config.json. Changing it
logs out every browser/phone that was signed in. The running API picks the
change up automatically (no restart needed).

Options:
    --trusted-proxy IP   also trust X-Forwarded-For from this reverse proxy
                         (used for per-client login rate limiting)
"""
import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from src.services.config_service import ConfigService  # noqa: E402
from src.services.auth_service import AuthService, MIN_PASSWORD_LENGTH  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description='Set the Strop controller password')
    parser.add_argument('--trusted-proxy', action='append', default=[],
                        help='reverse proxy IP whose X-Forwarded-For header is trusted')
    args = parser.parse_args()

    config = ConfigService()
    auth = AuthService(config)
    print(f"Config file: {config.config_path}")
    if auth.is_configured():
        print("A password is already set; it will be replaced and all sessions logged out.")

    while True:
        password = getpass.getpass(f"New password (min {MIN_PASSWORD_LENGTH} characters): ")
        if len(password) < MIN_PASSWORD_LENGTH:
            print("Too short, try again.")
            continue
        if getpass.getpass("Repeat password: ") != password:
            print("Passwords do not match, try again.")
            continue
        break

    auth.set_password(password)
    if args.trusted_proxy:
        proxies = sorted(set(config.get('auth.trusted_proxies', []) or []) | set(args.trusted_proxy))
        config.update('auth.trusted_proxies', proxies)
        print(f"Trusted proxies: {', '.join(proxies)}")
    print("Password saved.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
