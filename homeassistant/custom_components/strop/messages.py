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


# ---------------------------------------------------------------------- next run text
DAYS = {
    "ro": ["luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}
MONTHS = {
    "ro": ["ian.", "feb.", "mar.", "apr.", "mai", "iun.", "iul.", "aug.", "sept.", "oct.", "nov.", "dec."],
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
}
NEXT = {
    "ro": {"off": "Program oprit", "none": "Fără program", "today": "azi", "tomorrow": "mâine",
           "skipped": "sărită ({reason})", "watering": "Udă acum"},
    "en": {"off": "Schedule off", "none": "No schedule", "today": "today", "tomorrow": "tomorrow",
           "skipped": "skipped ({reason})", "watering": "Watering now"},
}
SHORT_REASONS = {
    "ro": {"frost": "îngheț", "cold": "prea frig", "not_needed.rain": "ploaie", "not_needed.humidity": "umiditate",
           "not_needed.temp": "vreme rece", "too_short": "prea scurtă"},
    "en": {"frost": "frost", "cold": "too cold", "not_needed.rain": "rain", "not_needed.humidity": "humidity",
           "not_needed.temp": "cool weather", "too_short": "too short"},
}


def short_reason(plan: dict[str, Any], lang: str) -> str:
    key = plan.get("reason_key") or ""
    if key == "not_needed":
        key = f"not_needed.{(plan.get('reason_args') or {}).get('factor', 'rain')}"
    return SHORT_REASONS.get(lang, SHORT_REASONS["en"]).get(key) or (plan.get("reason") or "?")


def next_run_text(schedule: dict[str, Any], at, today, lang: str) -> str:
    """Human readable state of the next run: 'Program oprit', 'vineri 13 nov., 05:35 · 6 min', ..."""
    n = NEXT.get(lang, NEXT["en"])
    if not schedule.get("cron_expression"):
        return n["none"]
    planned = schedule.get("planned") or []
    if not schedule.get("enabled") or not planned or at is None:
        return n["off"]
    plan = planned[0]
    diff = (at.date() - today).days
    if diff == 0:
        day = n["today"]
    elif diff == 1:
        day = n["tomorrow"]
    else:
        day = f"{DAYS.get(lang, DAYS['en'])[at.weekday()]} {at.day} {MONTHS.get(lang, MONTHS['en'])[at.month - 1]}"
    when = f"{day}, {at:%H:%M}"
    what = n["skipped"].format(reason=short_reason(plan, lang)) if plan.get("skip") else _minutes(plan.get("duration"))
    return f"{when} · {what}"
