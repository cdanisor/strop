"""Notification texts (Romanian / English) for Strop events."""
from __future__ import annotations

from typing import Any


def _minutes(seconds: Any) -> str:
    try:
        seconds = int(seconds or 0)
    except (TypeError, ValueError):
        return "?"
    if seconds < 60:
        return f"{seconds} s"
    m, s = divmod(seconds, 60)
    return f"{m} min" + (f" {s} s" if s and m < 10 else "")


REASONS = {
    "ro": {
        "frost": "risc de îngheț (minima {min}°C)",
        "cold": "prea frig pentru iarbă ({temp}°C medie)",
        "not_needed.temp": "nu e necesar: vreme rece",
        "not_needed.humidity": "nu e necesar: umiditate mare",
        "not_needed.rain": "nu e necesar: ploaie ({rain} mm)",
        "too_short": "rularea ajustată ar fi prea scurtă",
        "no_data": "fără date meteo",
    },
    "en": {
        "frost": "frost risk (min {min}°C)",
        "cold": "too cold for grass ({temp}°C avg)",
        "not_needed.temp": "not needed: cool weather",
        "not_needed.humidity": "not needed: high humidity",
        "not_needed.rain": "not needed: rain ({rain} mm)",
        "too_short": "adjusted run too short",
        "no_data": "no weather data",
    },
}

TEXT = {
    "ro": {
        "title": "Strop",
        "zone": "Zona {n}",
        "run_started": "{zone} udă {dur}{adj}.",
        "run_started_adj": " ({pct}% din {base}, ajustat după vreme)",
        "run_started_manual": "{zone} pornită manual pentru {dur}.",
        "run_finished": "{zone} a terminat de udat ({dur}).",
        "run_finished_stopped": "{zone} a fost oprită manual după {dur}.",
        "run_skipped": "Udarea programată pentru {zone} a fost sărită: {reason}.",
        "watchdog": "Watchdog: {zone} a fost închisă forțat după {dur}. Verifică instalația!",
        "weather_stale": "Datele meteo nu s-au mai actualizat de {hours} ore; ajustarea udării folosește prognoze vechi.",
        "controller_started": "Controllerul Strop a pornit (sau a fost repornit).",
    },
    "en": {
        "title": "Strop",
        "zone": "Zone {n}",
        "run_started": "{zone} watering for {dur}{adj}.",
        "run_started_adj": " ({pct}% of {base}, weather adjusted)",
        "run_started_manual": "{zone} started manually for {dur}.",
        "run_finished": "{zone} finished watering ({dur}).",
        "run_finished_stopped": "{zone} was stopped manually after {dur}.",
        "run_skipped": "Scheduled watering for {zone} was skipped: {reason}.",
        "watchdog": "Watchdog: {zone} was force-closed after {dur}. Please check the system!",
        "weather_stale": "Weather data has not been updated for {hours} hours; the watering adjustment uses old forecasts.",
        "controller_started": "The Strop controller started (or restarted).",
    },
}


def reason_text(payload: dict[str, Any], lang: str) -> str:
    key = payload.get("reason_key") or ""
    args = payload.get("reason_args") or {}
    if key == "not_needed":
        key = f"not_needed.{args.get('factor', 'rain')}"
    template = REASONS.get(lang, REASONS["en"]).get(key)
    if template is None:
        return payload.get("reason") or "?"
    try:
        return template.format(**args)
    except (KeyError, IndexError):
        return template


def event_message(kind: str, payload: dict[str, Any], lang: str) -> tuple[str, str]:
    t = TEXT.get(lang, TEXT["en"])
    zone = t["zone"].format(n=payload.get("valve_id", "?"))
    dur = _minutes(payload.get("duration"))
    if kind == "run_started":
        if payload.get("source") == "manual":
            msg = t["run_started_manual"].format(zone=zone, dur=dur)
        else:
            pct = payload.get("percent")
            adj = ""
            if pct is not None and pct < 100 and payload.get("base_duration"):
                adj = t["run_started_adj"].format(pct=pct, base=_minutes(payload.get("base_duration")))
            msg = t["run_started"].format(zone=zone, dur=dur, adj=adj)
    elif kind == "run_finished":
        key = "run_finished_stopped" if payload.get("status") == "stopped" else "run_finished"
        msg = t[key].format(zone=zone, dur=dur)
    elif kind == "run_skipped":
        msg = t["run_skipped"].format(zone=zone, reason=reason_text(payload, lang))
    elif kind == "watchdog":
        msg = t["watchdog"].format(zone=zone, dur=dur)
    elif kind == "weather_stale":
        msg = t["weather_stale"].format(hours=payload.get("hours", "?"))
    else:
        msg = t.get(kind, kind)
    return t["title"], msg
