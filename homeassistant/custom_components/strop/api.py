"""Small async client for the Strop REST API."""
from __future__ import annotations

from typing import Any

import aiohttp


class StropError(Exception):
    """Generic Strop API error."""


class StropAuthError(StropError):
    """Invalid password or token."""


class StropConnectionError(StropError):
    """Controller unreachable."""


class StropClient:
    def __init__(self, session: aiohttp.ClientSession, url: str, token: str | None = None) -> None:
        self._session = session
        self._base = url.rstrip("/")
        if not self._base.endswith("/api"):
            self._base += "/api"
        self.token = token

    async def _request(self, method: str, path: str, json: Any = None, auth: bool = True) -> dict:
        headers = {}
        if auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            async with self._session.request(
                method, self._base + path, json=json, headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                try:
                    data = await resp.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError):
                    data = {}
                if resp.status == 401:
                    raise StropAuthError(data.get("message", "Unauthorized"))
                if resp.status >= 400:
                    raise StropError(data.get("message") or f"HTTP {resp.status}")
                return data or {}
        except (aiohttp.ClientError, TimeoutError) as err:
            raise StropConnectionError(str(err)) from err

    # ------------------------------------------------------------------ auth / setup
    async def login(self, password: str) -> str:
        data = await self._request("POST", "/auth/login", {"password": password}, auth=False)
        return data["token"]

    async def create_integration_token(self, session_token: str, name: str) -> str:
        self.token = session_token
        data = await self._request("POST", "/auth/integration-tokens", {"name": name})
        self.token = data["token"]
        return self.token

    async def set_webhook(self, name: str, url: str) -> None:
        await self._request("POST", "/integrations/webhooks", {"name": name, "url": url})

    async def remove_webhook(self, name: str) -> None:
        await self._request("DELETE", f"/integrations/webhooks/{name}")

    # ------------------------------------------------------------------ data / control
    async def dashboard(self) -> dict:
        return await self._request("GET", "/dashboard")

    async def activate(self, valve_id: int, seconds: int) -> None:
        await self._request("POST", f"/valves/{valve_id}/activate", {"duration": int(seconds)})

    async def deactivate(self, valve_id: int) -> None:
        await self._request("POST", f"/valves/{valve_id}/deactivate")

    async def set_schedules_enabled(self, valve_id: int, enabled: bool) -> None:
        """Turn all schedules of a zone on or off."""
        await self._request("POST", f"/valves/{valve_id}/schedules/enabled", {"enabled": bool(enabled)})

    async def set_schedule(self, valve_id: int, cron: str, duration: int, enabled: bool) -> None:
        await self._request("POST", f"/valves/{valve_id}/cron",
                            {"cron_expression": cron, "duration": int(duration), "enabled": bool(enabled)})
