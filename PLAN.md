# Implementation Plan

Decisions locked in before this plan (see README for full requirements):

- **Transfer tracking:** manual "Start Transfer" / "Stop Transfer" button in the GUI is the source of truth.
- **Sensors:** none installed yet. Phase 1 is manual GUI entry only; the sensor POST API is built early but stays unused/untested against real hardware until sensors exist.
- **Notifications:** email (SMTP) for v1. Push (Pushover/Firebase) is a later add-on, not built now.
- **Deployment:** single Docker Compose service on a home server/NAS/Raspberry Pi, SQLite file on a mounted volume. No external reachability assumed, so no HTTPS/auth hardening beyond a simple sensor API key.
- **Weather provider:** OpenWeatherMap (free tier covers current + 5 day/3h forecast), accessed through a small provider interface so it can be swapped later.
- **Background jobs:** run in-process with APScheduler inside the Flask app (one container). No Celery/Redis — data volume is far too low to justify a second moving part.
- **Desired home temperature:** a configurable target (`desired_home_temp_c`). Once Home reaches it, a start notification is suppressed (no point transferring more heat), and if a transfer is already active, a stop notification is sent instead.
- **Configuration:** operational settings (location, thresholds, SMTP, weather API key) live in a DB-backed `Settings` row, not `.env`, so they can be set through a first-run wizard and edited later without a container restart. `.env` is reserved for true bootstrap values (Flask secret key, DB path, port).

## Repository layout (target)

```
app/
  __init__.py          # Flask app factory, registers blueprints + scheduler
  extensions.py        # db (SQLAlchemy), mail, scheduler singletons
  models.py            # Settings, TemperatureReading, WeatherObservation,
                        # WeatherForecast, HeatTransferEvent, NotificationLog
  api/                 # blueprint: POST /api/v1/readings (sensor ingestion)
  web/                 # blueprint: setup wizard, dashboard, manual entry,
                        # transfers, roadmap, settings
  services/
    weather.py         # OpenWeatherMap client behind a ProviderInterface
    notifications.py   # threshold check + email sender + cooldown state machine
    transfers.py        # start/stop logic, effectiveness calculation
    predictions.py      # forecast -> predicted transfer windows
  templates/, static/
migrations/             # Flask-Migrate/Alembic
tests/
config.py
wsgi.py
Dockerfile
docker-compose.yml
.env.example
```

## Phase 1 — Foundation & data model

- Scaffold Flask app (app factory pattern), SQLAlchemy, Flask-Migrate, pytest.
- Define core tables:
  - `Settings(id=1, location_name, latitude, longitude, weather_api_key, delta_threshold_c, desired_home_temp_c, renotify_cooldown_min, notify_email, smtp_host, smtp_port, smtp_username, smtp_password, smtp_use_tls, is_configured)` — single row, created by the setup wizard (Phase 2).
  - `TemperatureReading(id, location[home|conservatory|<custom>], value_c, source[manual|sensor], sensor_id, recorded_at)`
  - `WeatherObservation(id, fetched_at, temp_c, cloud_pct, humidity, wind, condition, raw_json)`
  - `WeatherForecast(id, fetched_at, forecast_for, temp_c, cloud_pct, condition, raw_json)`
  - `HeatTransferEvent(id, started_at, ended_at, home_temp_start, home_temp_end, conservatory_temp_start, conservatory_temp_end, effectiveness, notes)`
  - `NotificationLog(id, sent_at, kind[start|stop], delta_c, home_temp, success)`
- Dockerfile + docker-compose.yml (single service, SQLite on a named volume), `.env.example` limited to `SECRET_KEY`, `DATABASE_PATH`, `PORT`.
- Health check route (`/healthz`).

**Exit criteria:** `docker-compose up -d` starts an empty app with a migrated DB (no `Settings` row yet).

## Phase 2 — First-run setup wizard

- Middleware/`before_request` check: if no `Settings` row exists (or `is_configured` is false), every route except the wizard itself and static assets redirects to `/setup`.
- Multi-step wizard (session-backed, one POST/redirect per step, back/next navigation):
  1. **Location** — search by address/city ("Find coordinates" button, backed by Open-Meteo's free key-less geocoding API so it works before the weather API key is collected) and pick a match, or enter lat/lon directly.
  2. **Weather API** — paste the OpenWeatherMap API key; "Test connection" does a live current-conditions fetch to confirm it works before continuing.
  3. **Notification rules** — delta threshold (default 3°C), desired home temperature, re-notify cooldown minutes.
  4. **Email delivery** — SMTP host/port/username/password/from-address/use-TLS, recipient address; "Send test email" button.
  5. **Review & confirm** — summary of all entered values; "Finish setup" writes the `Settings` row with `is_configured = true` and redirects to the dashboard.
- A `/settings` page (normal nav item, not the step wizard) reuses the same form sections so any value can be changed later without re-running first-run setup.
- All later phases (weather jobs, notification rule engine, sensor auth) read their config from `Settings`, never from `.env` or hardcoded defaults.

**Exit criteria:** a fresh `docker-compose up -d` against an empty DB forces you through the wizard before the dashboard or any API becomes usable; every value entered is editable afterwards from `/settings`.

## Phase 3 — Manual entry + sensor ingestion + basic dashboard

- GUI form to log a Home/Conservatory/custom-location reading (defaults to now, optional timestamp override for backfill).
- `POST /api/v1/readings` — header-based API key, body `{location, value_c, sensor_id, recorded_at?}`, for future ESP8266 sensors.
- `GET` endpoints backing the dashboard: latest reading per location, history for a time range.
- Dashboard page: current temp per location as large tiles, 24–48h line chart (Chart.js).

**Exit criteria:** you can log temps by hand and see them plotted; the same endpoint a sensor would hit is exercised via curl/Postman.

## Phase 4 — Weather data ingestion

- `WeatherProvider` interface + `OpenWeatherMapProvider` implementation (current conditions + 5-day/3h forecast), reading location + API key from `Settings`.
- APScheduler jobs: fetch current weather every 30 min, forecast every 3h; persist to `WeatherObservation` / `WeatherForecast`.
- Add outdoor conditions to the dashboard.

**Exit criteria:** weather rows accumulate automatically without user action.

## Phase 5 — Notification rule engine

- Scheduled job (every 5–10 min): compare latest Conservatory vs Home reading against `Settings.delta_threshold_c`, and Home vs `Settings.desired_home_temp_c`.
- State machine per "warm window" (`idle → notified → cooldown/active`) so a sustained delta only triggers one email, not one per poll; re-notify interval from `Settings.renotify_cooldown_min` if still above threshold and no transfer started.
- Desired-temp guard on the **start** notification: even if delta ≥ threshold, suppress the start email while Home ≥ `Settings.desired_home_temp_c` (no benefit to transferring more heat).
- Desired-temp trigger on the **stop** notification: while a transfer is active (see Phase 6), if Home reaches `Settings.desired_home_temp_c`, send a one-off "stop transfer" email regardless of the current Conservatory/Home delta.
- SMTP email sender (using `Settings` SMTP fields) with templates for both kinds (start: current temps, delta, timestamp; stop: Home temp, desired temp reached, transfer duration so far); log every send attempt to `NotificationLog` with its `kind`.

**Exit criteria:** crossing the delta threshold reliably produces exactly one start email until you either start a transfer or the delta drops back below threshold; once Home reaches the desired temperature, no further start emails fire, and an active transfer gets exactly one stop email.

## Phase 6 — Heat transfer tracking

- "Start Transfer" button (surfaced prominently when a notification is active) and "Stop Transfer" button.
- On start: snapshot start time + both temps. On stop: snapshot end time + both temps, compute duration.
- Expose "is a transfer currently active" to the Phase 5 rule engine (single row/flag query) so it can decide whether to send the stop-at-desired-temp email.
- Effectiveness v1: Home temperature rise over the transfer duration (simple, defensible, revisit once there's enough history for a baseline-decay comparison).
- Event log page: table of past transfers + detail view; allow editing/deleting a mis-logged event.
- Overlay transfer windows on the dashboard's temperature chart.

**Exit criteria:** a full manual transfer cycle is logged end-to-end and visible in the event log.

## Phase 7 — Predictions & roadmap

- Once enough history exists (a few weeks), train a simple regression (scikit-learn) predicting Conservatory temp rise and Home decay from outdoor temp, cloud cover, hour-of-day, season; retrain nightly.
- Fallback heuristic when data is insufficient (e.g., sunny + outdoor temp above X → likely Conservatory warming) so the roadmap isn't empty on day one.
- Roadmap generation: for each upcoming forecast slot (next 3–5 days), predict both temps, flag delta ≥ threshold as a predicted opportunity with a confidence indicator.
- Roadmap page: timeline/table view highlighting predicted good windows and expected effectiveness.

**Exit criteria:** roadmap page shows a multi-day outlook that updates as new forecasts and history come in.

## Phase 8 — Polish & hardening

- Per-sensor API keys, basic rate limiting on the ingestion endpoint.
- Mobile-friendly layout pass, input validation on manual entry and on the wizard/settings forms.
- README updated with real setup/run instructions; `.env.example` finalized.
- Note on SQLite volume backup (single file, easy to snapshot).
- Optional: lightweight session login for the GUI if ever exposed outside the LAN.

## Deferred / explicitly out of scope for now

- Push notifications (Pushover/Firebase) — add as a second sender function behind the existing notification step once email is proven out.
- Multi-provider weather fallback (WeatherAPI/AccuWeather) — the interface supports it, but only one provider ships initially.
- Any multi-user/auth system beyond a single sensor API key.
