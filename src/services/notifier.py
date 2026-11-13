"""
Event notifications for integrations (Home Assistant).

Strop POSTs a small JSON document to every registered webhook when something
happens. Delivery runs on a background thread with a short timeout so a slow
or offline receiver can never delay valve control.

Events:
    controller_started  {}
    run_started         {valve_id, duration, base_duration, percent, source}
    run_finished        {valve_id, duration, status}
    run_skipped         {valve_id, base_duration, reason_key, reason_args, reason}
    weather_stale       {hours}

Webhooks live in config.json under "integrations.webhooks" as
{"name": ..., "url": ...} and are managed through the API.
"""
import json
import logging
import queue
import threading
import urllib.request
from datetime import datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

TIMEOUT = 5
MAX_QUEUE = 100

STATUS_NAMES = {
    'Finished': 'finished',
    'Manually Stopped': 'stopped',
    'Terminated': 'terminated',
    'Watchdog Stopped': 'watchdog',
}


class Notifier:
    def __init__(self, config_service=None):
        self.config_service = config_service
        self._queue: "queue.Queue" = queue.Queue(maxsize=MAX_QUEUE)
        self._thread = threading.Thread(target=self._worker, name='strop-notifier', daemon=True)
        self._thread.start()

    # ------------------------------------------------------------------ webhooks
    def webhooks(self) -> List[Dict[str, str]]:
        if self.config_service is None:
            return []
        return list(self.config_service.get('integrations.webhooks', []) or [])

    def set_webhook(self, name: str, url: str) -> None:
        if not url.startswith(('http://', 'https://')):
            raise ValueError('Webhook URL must start with http:// or https://')
        hooks = [h for h in self.webhooks() if h.get('name') != name]
        hooks.append({'name': name, 'url': url})
        self.config_service.update('integrations.webhooks', hooks)

    def remove_webhook(self, name: str) -> bool:
        hooks = self.webhooks()
        kept = [h for h in hooks if h.get('name') != name]
        if len(kept) == len(hooks):
            return False
        self.config_service.update('integrations.webhooks', kept)
        return True

    # ------------------------------------------------------------------ events
    def emit(self, event: str, **data: Any) -> None:
        """Queue an event for delivery; never raises, never blocks."""
        try:
            hooks = self.webhooks()
            if not hooks:
                return
            payload = {'event': event, 'time': datetime.now().astimezone().isoformat(), **data}
            if 'valve_id' in data and hasattr(self.config_service, 'zone_name'):
                payload.setdefault('zone_name', self.config_service.zone_name(data['valve_id']))
            for hook in hooks:
                self._queue.put_nowait((hook.get('url'), payload))
        except queue.Full:
            logger.warning("Notification queue full, dropping event %s", event)
        except Exception as e:
            logger.error("Could not queue event %s: %s", event, e)

    def valve_event(self, kind: str, valve_id: int, **data: Any) -> None:
        """Callback used by the GPIO service."""
        if kind == 'opened':
            meta = data.get('meta') or {}
            self.emit('run_started', valve_id=valve_id, duration=data.get('duration'),
                      base_duration=meta.get('base_duration'), percent=meta.get('adjust_percent'),
                      source='schedule' if meta else 'manual')
        elif kind == 'closed':
            self.emit('run_finished', valve_id=valve_id, duration=data.get('duration'),
                      status=STATUS_NAMES.get(data.get('status'), data.get('status')))

    def flush(self, timeout: float = 5.0) -> None:
        """Wait until queued events were delivered (tests, shutdown)."""
        done = threading.Event()
        self._queue.put((None, done))
        done.wait(timeout)

    def _worker(self) -> None:
        while True:
            url, payload = self._queue.get()
            if url is None:
                payload.set()
                continue
            try:
                req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                             headers={'Content-Type': 'application/json'}, method='POST')
                with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                    resp.read()
            except Exception as e:
                logger.warning("Webhook delivery of %s failed: %s", payload.get('event'), e)
