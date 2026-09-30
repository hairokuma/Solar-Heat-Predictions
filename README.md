# Solar-Heat-Predictions

I want to collect data based on weather apis and also collect my own measurements of temperatures from in Home, Conservatory and Garden.
The goal is to analyze the correlation between external weather conditions and the internal temperatures of different areas of my property.
To make predictions when and for how long I can benefit from solar heat from the Conservatory to heat the Home.

In case the Conservatory is ~3°C warmer than the Home, I want to start the heat transfer from the Conservatory to the Home.
The heat transfer is a manual step therefore I need to be notified via email or push notification when the Conservatory is sufficiently warmer than the Home.

Additionally, I want to track the duration and effectiveness of each heat transfer event to further refine my predictions and optimize the use of solar heat.
Also a goal would be to get a roadmap of the next few days regarding the expected solar heat availability and potential heat transfer opportunities, based on my collected data and weather forecasts.

See [PLAN.md](PLAN.md) for the phased implementation plan this was built against.

## Quickstart (Docker)

```sh
cp .env.example .env
# edit .env: set SECRET_KEY to a random value

docker-compose up -d
```

Open `http://<host>:5000` (or whatever `PORT` you set in `.env`, default 5000). A fresh instance
redirects straight to a first-run setup wizard - location, weather API key
([OpenWeatherMap](https://openweathermap.org/api), free tier is enough), notification thresholds,
and SMTP details for the email alert. Everything the wizard collects (and only that - no other
secrets) lives in the database from then on and is editable later from **Settings**, so the
container never needs to be rebuilt or restarted to change configuration.

## Local development

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

export FLASK_APP=wsgi:app
export SECRET_KEY=dev
.venv/bin/flask db upgrade      # creates instance/app.db

.venv/bin/python wsgi.py        # dev server on http://127.0.0.1:5000
```

Run the tests with:

```sh
.venv/bin/python -m pytest
```

After changing `app/models.py`, generate and review a migration before committing:

```sh
.venv/bin/flask db migrate -m "describe the change"
.venv/bin/flask db upgrade
```

## Connecting a sensor

Each physical sensor (e.g. an ESP8266 with a DHT11/NTC 10kΩ) is registered individually from
**Settings → Sensors**, which assigns it its own API key and binds it to one location
(Home, Conservatory, or a custom location added under **Settings → Locations**). Revoking a sensor immediately invalidates just that key.
See [docs/esp8266-sensor.md](docs/esp8266-sensor.md) for wiring and firmware for one ESP8266
reading a DHT11 (Home) and an NTC (Conservatory).

```
POST /api/v1/readings
X-API-Key: <the sensor's key>
Content-Type: application/json

{"value_c": 23.4, "humidity_pct": 55.0}
```

`humidity_pct` is optional (0–100). It can also be entered by hand in the dashboard's
log-reading dialog, and is plotted on the chart's right-hand axis.

The ingestion endpoint is rate-limited (60 requests/minute per API key) to absorb a
misbehaving or misconfigured device without affecting other sensors.

## Architecture notes

- **Single process by design.** Weather ingestion and the notification rule engine run as
  in-process [APScheduler](https://apscheduler.readthedocs.io/) background jobs (see
  `app/scheduler.py`), not a separate worker. This is why `entrypoint.sh` runs gunicorn with
  `--workers 1` - a second worker process would start its own copy of every scheduled job and
  duplicate weather fetches and notification emails. For a single-user home app this is a
  reasonable trade-off against the complexity of a real task queue.
- **Predictions are trained on demand**, not cached or scheduled nightly. At this app's data
  scale (a personal home's worth of readings), fitting the regression in `app/services/predictions.py`
  takes single-digit milliseconds on every `/roadmap` request, so there's no persisted model to
  go stale.
- **LAN-only threat model.** There's no login system; anyone who can reach the app can see and
  change everything, including SMTP credentials. This is intentional for a home-network
  deployment. If you ever expose this beyond your LAN, put it behind a reverse proxy with its own
  authentication (e.g. Caddy/nginx with basic auth, or a private network like Tailscale/WireGuard)
  rather than relying on anything in this app.

## Backup

Everything lives in one SQLite file, mounted as the `solar-heat-data` Docker volume at
`/data/app.db`. To back it up:

```sh
# Safe to run while the container is up - .backup takes a consistent snapshot.
docker compose exec app sqlite3 /data/app.db ".backup /data/backup-$(date +%F).db"
docker cp $(docker compose ps -q app):/data/backup-$(date +%F).db .
```

Or simpler, while the container is stopped: copy the volume's file directly
(`docker volume inspect solar-heat-predictions_solar-heat-data` shows its mountpoint).

## Data Collection

- Weather data from APIs (e.g., OpenWeatherMap, WeatherAPI, AccuWeather)
- Temperature measurements from Home and Conservatory, plus any custom logging-only locations (Manually in the GUI and automatically via sensors -> POST API)

## Notifications

- Email or push notifications when the Conservatory is sufficiently warmer than the Home

## Heat Transfer Tracking

- Duration and effectiveness of each heat transfer event

## Predictions and Roadmap

- Forecast of solar heat availability and potential heat transfer opportunities based on collected data and weather forecasts
- See [docs/predictions.md](docs/predictions.md) for how the forecast and predictions work

## Web GUI

- Interface for manual input of temperature measurements
- Display of current temperatures in Home, Conservatory, and any custom locations
- Notifications for heat transfer opportunities
- Logging and visualization of heat transfer events
- Display of predicted solar heat availability and potential heat transfer opportunities

## tech

- Sensors: Temperature sensors for Home, Conservatory, and optionally custom locations (for automatic data collection) (e.g., ESP8266 with DHT22 or DS18B20)
- Programming languages: Python, JavaScript
- Frameworks: Flask (for web GUI and API), HTML, CSS, JavaScript (for frontend),
- Databases: SQLite (for storing temperature measurements and heat transfer events)
- APIs: OpenWeatherMap, WeatherAPI, AccuWeather (for weather data)
- Notification services: Email (SMTP) or push notifications (e.g., Pushover, Firebase)
- Platform: Docker (for containerization and deployment)

## Deployment

```sh
docker-compose up -d
```
