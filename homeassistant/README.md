# Strop – Home Assistant integration

Custom integration that connects Home Assistant to the Strop irrigation
controller: control, sensors, push events and phone notifications.

## Install

1. Copy `custom_components/strop` into the Home Assistant config folder
   (`/config/custom_components/strop`) and restart Home Assistant.
2. *Settings → Devices & services → Add integration → Strop Irrigation*.
3. Enter
   - **Strop API URL**, e.g. `http://192.168.10.17:5000`
   - **Strop password** – used once to create a dedicated long-lived token
     (`home-assistant`); the password itself is not stored in Home Assistant
   - **Home Assistant URL reachable from Strop**, e.g. `http://192.168.10.14:8209`
     (Strop pushes events to a webhook at this address)
4. Optional: *Configure* the integration to choose a notification service
   (e.g. `notify.mobile_app_<phone>`), which events to be notified about and
   the message language (Romanian / English).

## Entities

| Entity | Description |
|---|---|
| `switch.strop_zone_N` | On: water now for the "manual duration"; Off: stop |
| `switch.strop_zone_N_schedule` | Enable / disable the zone's schedule |
| `number.strop_zone_N_manual_duration` | Minutes used by the zone switch (1–60) |
| `binary_sensor.strop_zone_N_watering` | Valve open |
| `sensor.strop_zone_N_remaining` | Time left of the current run |
| `sensor.strop_zone_N_next_run` | Next run as text: "Schedule off", "Friday 13 Nov, 05:35 · 6 min", "… · skipped (rain)" (attributes: exact time, programmed and adjusted minutes, %, reason) |
| `sensor.strop_weather_adjustment` | % of programmed time for the next run day (attributes: temperature, humidity, rain and their effect) |
| `sensor.strop_watered_today` | Total watering time today |
| `sensor.strop_forecast_updated` | Last weather update |

(Entity ids depend on the Home Assistant language; names are translated.)

## Events for automations

Every event from Strop is fired on the bus as `strop_event`, with `type` one of
`run_started`, `run_finished`, `run_skipped`, `watchdog`, `weather_stale`,
`controller_started` and the event data (`valve_id`, `duration`,
`base_duration`, `percent`, `source`, `status`, `reason_key`, `reason`, …).

```yaml
trigger:
  - platform: event
    event_type: strop_event
    event_data:
      type: run_skipped
```

## Revoking access

The integration's token can be revoked on Strop with
`DELETE /api/auth/integration-tokens/home-assistant`; Home Assistant then asks
to re-authenticate. Removing the integration also unregisters its webhook.
