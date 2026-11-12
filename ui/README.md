# Strop UI

Single-page dashboard for the irrigation controller: zone status with a live
countdown, manual watering, weekly schedules, recent activity and a 12-day
weather / watering strip.

## Files

- `index.html` – markup, inline SVG icon sprite, zone template
- `styles.css` – all styling (light/dark via CSS variables, no framework)
- `app.js` – vanilla JavaScript, no dependencies
- `server.py` – tiny static server that injects `api_url` from `config.json`

No build step and no CDN: the page works on a LAN without internet access.

## Built for the Raspberry Pi 1

- The whole page is built from one request, `GET /api/dashboard`.
- While idle the page polls only `GET /api/valves/status` every 15 s and
  reloads the dashboard when a valve changes state (or every 5 minutes).
- Polling pauses while the tab is hidden; countdowns run in the browser.
- Static files are cached by the browser for a day; bump the `?v=` number
  in `index.html` when `styles.css` or `app.js` change.
- `server.py` does not write access logs (spares the SD card).

## Run locally

```bash
python src/api_server.py      # API on :5000 (GPIO simulated off the Pi)
python ui/server.py           # UI on :8000
```
