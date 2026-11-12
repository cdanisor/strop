"""
Weather-based reduction of scheduled watering time.

Method
------
Based on the Zimmerman method used by OpenSprinkler: the programmed duration
is scaled by a percentage computed from temperature, humidity and rain
relative to a baseline day on which the programmed duration is exactly right:

    percent = 100 + temp_term + humidity_term + rain_term

    temp_term     = (T - base_temp)      * temp_pct_per_c
    humidity_term = (base_humidity - H)  * humidity_pct_per_pct
    rain_term     = -R                   * rain_pct_per_mm

Adaptations for this garden:
  * metric units; Zimmerman's 2 % per 0.01 inch of rain is 7.87 % per mm, so
    ~12.7 mm (half an inch, a common "skip" threshold) cancels a run;
  * Zimmerman's 4 % per degree F (7.2 % per degree C) is widely reported as
    too aggressive, so half of it is used by default (3.6 % per degree C);
  * the baseline is a typical Bucharest summer day (22 C mean, 55 % humidity)
    instead of Zimmerman's 70 F / 30 %;
  * rain is a weighted sum over the two previous days, the run day and the two
    next days (forecasts weighted down for uncertainty), similar to smart
    controllers that skip on rain in the last and next 24 h;
  * the result is capped at 100 %: the schedule is only ever reduced;
  * hard skips: frost risk (run day minimum <= 2 C), dormant/cold grass
    (mean temperature below 8 C), or a result below 20 % (too short to soak in).

All parameters can be overridden in config.json under "watering_adjustment".
"""
from datetime import date, timedelta
from typing import Any, Dict, Iterable, Optional

DEFAULTS: Dict[str, Any] = {
    'enabled': True,
    'base_temp': 22.0,              # C, mean daily temperature of the baseline day
    'base_humidity': 55.0,          # %, mean daily humidity of the baseline day
    'temp_pct_per_c': 3.6,          # % change per degree C away from base_temp
    'humidity_pct_per_pct': 1.0,    # % change per % humidity away from base_humidity
    'rain_pct_per_mm': 7.87,        # % reduction per mm of effective rain
    # weight of each day's rain, relative to the run day (0)
    'rain_weights': {-2: 0.5, -1: 1.0, 0: 1.0, 1: 0.5, 2: 0.25},
    'freeze_temp': 2.0,             # C, skip when the run day minimum is at or below
    'cold_temp': 8.0,               # C, skip when the mean temperature is below
    'min_percent': 20.0,            # %, skip when the result is below
    'min_run_seconds': 60,          # skip runs shorter than this after adjustment
}


def settings(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg = dict(DEFAULTS)
    for key, value in (overrides or {}).items():
        if key == 'rain_weights' and isinstance(value, dict):
            cfg[key] = {int(k): float(v) for k, v in value.items()}
        elif key in cfg:
            cfg[key] = value
    return cfg


def _mean(values: Iterable[Optional[float]]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def compute_adjustment(weather_by_date: Dict[str, Dict[str, Any]], run_date: date,
                       config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Compute the watering percentage for a run on `run_date`.

    Args:
        weather_by_date: daily weather rows keyed by 'YYYY-MM-DD' with
            temperature_minimum, temperature_maximum, average_humidity, total_rain.
        run_date: the day the scheduled run happens.
        config: overrides for DEFAULTS.

    Returns a dict with: percent (0-100), skip (bool), reason (short text),
    terms (temp/humidity/rain in %), inputs (T, H, R, freeze minimum) and
    days_used.
    """
    cfg = settings(config)
    result = {
        'enabled': bool(cfg['enabled']),
        'date': run_date.isoformat(),
        'percent': 100,
        'skip': False,
        'reason': '',
        'terms': {'temp': 0.0, 'humidity': 0.0, 'rain': 0.0},
        'inputs': {'temp': None, 'humidity': None, 'rain': 0.0, 'min_temp': None},
        'days_used': [],
    }
    if not cfg['enabled']:
        result['reason'] = 'Weather adjustment disabled'
        return result

    def day(offset: int) -> Optional[Dict[str, Any]]:
        return weather_by_date.get((run_date + timedelta(days=offset)).isoformat())

    # Temperature and humidity: the day before and the run day
    climate_days = [d for d in (day(-1), day(0)) if d]
    means = [(d['temperature_minimum'] + d['temperature_maximum']) / 2 for d in climate_days
             if d.get('temperature_minimum') is not None and d.get('temperature_maximum') is not None]
    temp = _mean(means)
    humidity = _mean(d.get('average_humidity') for d in climate_days)

    if temp is None and humidity is None:
        result['reason'] = 'No weather data, full duration'
        return result

    # Weighted rain window
    rain = 0.0
    for offset, weight in cfg['rain_weights'].items():
        d = day(offset)
        if d:
            rain += float(d.get('total_rain') or 0) * float(weight)
            result['days_used'].append((run_date + timedelta(days=offset)).isoformat())
    today = day(0)
    min_temp = today.get('temperature_minimum') if today else None

    temp_term = (temp - cfg['base_temp']) * cfg['temp_pct_per_c'] if temp is not None else 0.0
    hum_term = (cfg['base_humidity'] - humidity) * cfg['humidity_pct_per_pct'] if humidity is not None else 0.0
    rain_term = -rain * cfg['rain_pct_per_mm']
    raw = 100.0 + temp_term + hum_term + rain_term
    percent = max(0.0, min(100.0, raw))

    result['terms'] = {'temp': round(temp_term, 1), 'humidity': round(hum_term, 1), 'rain': round(rain_term, 1)}
    result['inputs'] = {
        'temp': round(temp, 1) if temp is not None else None,
        'humidity': round(humidity) if humidity is not None else None,
        'rain': round(rain, 1),
        'min_temp': round(min_temp, 1) if min_temp is not None else None,
    }

    # Hard skips, most important first
    if min_temp is not None and min_temp <= cfg['freeze_temp']:
        result.update(percent=0, skip=True, reason=f'Frost risk (min {min_temp:.0f}°C)')
    elif temp is not None and temp < cfg['cold_temp']:
        result.update(percent=0, skip=True, reason=f'Too cold for grass ({temp:.0f}°C avg)')
    elif percent < cfg['min_percent']:
        main = min(result['terms'], key=result['terms'].get)
        label = {'temp': 'cool weather', 'humidity': 'high humidity', 'rain': f'rain ({rain:.0f} mm)'}[main]
        result.update(percent=0, skip=True, reason=f'Not needed: {label}')
    else:
        result['percent'] = int(round(percent))
        reductions = [(v, k) for k, v in result['terms'].items() if v <= -5]
        if reductions:
            labels = {'temp': 'cool', 'humidity': 'humid', 'rain': f'rain {rain:.0f} mm'}
            result['reason'] = ', '.join(labels[k] for _, k in sorted(reductions))
        else:
            result['reason'] = 'Normal conditions'
    return result


def adjusted_seconds(base_seconds: int, adjustment: Dict[str, Any],
                     config: Optional[Dict[str, Any]] = None) -> int:
    """Adjusted run length in seconds (0 means the run is skipped)."""
    cfg = settings(config)
    if adjustment.get('skip'):
        return 0
    seconds = int(round(base_seconds * adjustment.get('percent', 100) / 100.0 / 10.0) * 10)
    if seconds < cfg['min_run_seconds'] and adjustment.get('percent', 100) < 100:
        return 0
    return min(seconds, base_seconds)


class WateringAdjuster:
    """Reads weather from the database and config, computes adjustments."""

    def __init__(self, db, config_overrides: Optional[Dict[str, Any]] = None):
        self.db = db
        self.config = config_overrides or {}

    def _weather(self) -> Dict[str, Dict[str, Any]]:
        return {row['date']: row for row in self.db.get_all_daily_weather_data()}

    def for_date(self, run_date: date, weather: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
        return compute_adjustment(weather if weather is not None else self._weather(), run_date, self.config)

    def plan(self, base_seconds: int, run_date: date,
             weather: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
        """Adjustment for a run plus the resulting duration."""
        adj = self.for_date(run_date, weather)
        seconds = adjusted_seconds(base_seconds, adj, self.config)
        adj = dict(adj)
        adj['base_duration'] = base_seconds
        adj['duration'] = seconds
        if seconds == 0 and not adj['skip']:
            adj['skip'] = True
            adj['percent'] = 0
            adj['reason'] = 'Adjusted run too short'
        return adj
