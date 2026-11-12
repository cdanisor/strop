"""
Software watchdog for the Strop API process.

Two layers of protection against a valve staying open:

1. Valve guard (in-process): every few seconds each open valve is checked
   against its planned duration. A valve open longer than planned + grace
   (e.g. its timer thread died) is closed and logged as "Watchdog Stopped".
   The GPIO outputs are also compared with the expected valve state and any
   pin found HIGH for a closed valve is forced LOW.

2. systemd watchdog: with Type=notify and WatchdogSec= in the unit, the
   process must send WATCHDOG=1 regularly. It only does so while it is
   healthy (HTTP server answers, valve scheduler running). If the process
   hangs, systemd kills and restarts it; ExecStopPost runs
   src/gpio_safe_off.py so the relays are switched off immediately, and the
   restarted service initialises every pin LOW.

The Raspberry Pi hardware watchdog (systemd RuntimeWatchdogSec) covers a
frozen kernel/OS.
"""
import logging
import os
import socket
import threading
import time
import urllib.request

logger = logging.getLogger(__name__)

GRACE_SECONDS = 30          # extra time before a valve is force-closed
HEALTH_FAILURES_ALLOWED = 3  # consecutive failed self-checks before we stop petting systemd
STARTUP_GRACE = 90          # seconds during which HTTP check failures are tolerated


def sd_notify(message: str) -> bool:
    """Send a notification to systemd (no-op when not started by systemd)."""
    address = os.environ.get('NOTIFY_SOCKET')
    if not address:
        return False
    if address.startswith('@'):
        address = '\0' + address[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(address)
            sock.sendall(message.encode())
        return True
    except OSError as e:
        logger.warning("sd_notify failed: %s", e)
        return False


def watchdog_interval(default: float = 10.0) -> float:
    """Half of systemd's WatchdogSec (WATCHDOG_USEC), or `default`."""
    try:
        usec = int(os.environ.get('WATCHDOG_USEC', '0'))
    except ValueError:
        usec = 0
    if usec > 0:
        return max(1.0, usec / 1_000_000 / 2)
    return default


class Watchdog:
    def __init__(self, main_service, health_url: str = 'http://127.0.0.1:5000/api/health',
                 interval: float = None):
        self.main_service = main_service
        self.health_url = health_url
        self.interval = min(interval or watchdog_interval(), 10.0)
        self._stop = threading.Event()
        self._thread = None
        self._started_at = None
        self._health_failures = 0
        self._http_ok_once = False

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self._started_at = time.monotonic()
        self._thread = threading.Thread(target=self._run, name='strop-watchdog', daemon=True)
        self._thread.start()
        logger.info("Watchdog started (check every %.0f s)", self.interval)

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.tick()
            except Exception as e:  # the watchdog itself must never die
                logger.exception("Watchdog tick failed: %s", e)

    # ------------------------------------------------------------------ checks
    def tick(self) -> bool:
        """One round of checks; returns True if systemd was told we're healthy."""
        self.guard_valves()
        healthy = self.check_health()
        if healthy:
            sd_notify('WATCHDOG=1')
        return healthy

    def guard_valves(self) -> list:
        """Force-close valves open past their planned time; fix stray HIGH pins."""
        gpio = getattr(self.main_service, 'gpio_service', None)
        if gpio is None:
            return []
        closed = []
        for valve_id in (1, 2):
            details = gpio.get_valve_details(valve_id)
            if details.get('open'):
                planned = details.get('duration')
                started = gpio.valve_start_times.get(valve_id)
                if started is None:
                    continue
                from src.services.gpio_control_service import MAX_DURATION_SECONDS
                limit = (planned or MAX_DURATION_SECONDS) + GRACE_SECONDS
                elapsed = (time.time() - started.timestamp())
                if elapsed > limit:
                    logger.error("Watchdog: valve %s open for %ds (planned %ss), forcing it closed",
                                 valve_id, elapsed, planned)
                    gpio.deactivate_valve(valve_id, status='Watchdog Stopped')
                    closed.append(valve_id)
        gpio.verify_outputs()
        return closed

    def check_health(self) -> bool:
        ms = self.main_service
        if not getattr(ms, 'is_running', False):
            return False
        scheduler = getattr(ms, 'valve_scheduler', None)
        if scheduler is None or not scheduler.is_running or not scheduler.scheduler.running:
            logger.error("Watchdog: valve scheduler is not running")
            return False

        try:
            with urllib.request.urlopen(self.health_url, timeout=5) as resp:
                ok = resp.status == 200
        except Exception as e:
            ok = False
            err = e
        if ok:
            self._health_failures = 0
            self._http_ok_once = True
            return True

        in_startup = not self._http_ok_once and time.monotonic() - self._started_at < STARTUP_GRACE
        if in_startup:
            return True
        self._health_failures += 1
        logger.error("Watchdog: health check failed (%d/%d): %s",
                     self._health_failures, HEALTH_FAILURES_ALLOWED, err)
        return self._health_failures < HEALTH_FAILURES_ALLOWED
