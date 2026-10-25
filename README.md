# Day-ahead wind

A desk for a GB supplier’s day-ahead buyers. It shows the national wind forecast that was already published when the day-ahead order book closed, and it scores that forecast against metered outturn for every January 2026 delivery day.

Two routes: `/review` is one delivery day, `/accuracy` is the whole month. `/` opens `/review`.

## How the numbers are made

- Actuals are Elexon FUELHH, `fuelType=WIND`, half-hourly average MW.
- Forecasts are Elexon WINDFOR. Each publication is an hourly MW curve.
- The 09:50 Europe/London cutoff is a business assumption for the day-ahead buy, not a timestamp returned by Elexon. It is the N2EX order-book close used by this desk. For each hour of the delivery day the desk keeps the latest `publishTime` at or before that assumed gate. Anything published later is ignored. Two WINDFOR rows with the same publish time and the same hourly start are not added together. The last row wins, and a conflicting forecast is counted.
- `publishTime` and `startTime` must include `Z` or an explicit offset. A timestamp without a zone is left out; it is not treated as UTC. The settlement clock is Europe/London. A settlement period that does not match its interval timestamp is counted as a mismatch, and the period shown is taken from that timestamp. In January, London is GMT, so the UTC clock and the London clock match. The served extract stays January 2026. The interval builder still follows the Europe/London civil day, which has 46 half-hours on the spring clock change and 50 on the autumn clock change. Those days are not fetched or shown.
- WINDFOR is hourly. Only a `startTime` that lands exactly on a London hour is kept, and that MW value is held across both half-hours. A start one minute or one second off the hour is left out, not moved onto the hour. A missing forecast or actual stays blank. It is not filled with 0 MW.
- Energy error is the sum of `(forecast MW − actual MW) × 0.5` over matched half-hours. Positive and negative half-hours can cancel.
- Absolute energy error is the sum of the absolute half-hour energy errors. The signs do not cancel.
- The data-quality panel counts half-hour intervals, matched intervals, missing forecasts, and missing actuals.

The checked-in file `data/january_2026.json` is a snapshot pulled from those public endpoints, so the demo still runs if Elexon is down. On this snapshot every January half-hour has both an actual and a pre-gate forecast. The morning vintage used for a normal delivery day is 09:30 London, the last WINDFOR run before the assumed 09:50 gate.

## Directories

```
Dockerfile                  Single image: API and built UI, for hosting
docker-compose.yml          Local API on :8000 and UI on :8080
data/january_2026.json      Elexon snapshot for January 2026
backend/app/config.py       Delivery month and the 09:50 gate
backend/app/elexon.py       FUELHH and WINDFOR client, with retry on 429
backend/app/ingest.py       Day-by-day pull. Run as python -m app.ingest
backend/app/analysis.py     Pre-gate selection, bias, MAE, RMSE, energy
backend/app/store.py        Loads the snapshot once
backend/app/main.py         /api/health /api/meta /api/days /api/days/{date} /api/accuracy
backend/tests/              Gate, scoring, and API tests
frontend/src/pages/         Decision desk and accuracy screens
frontend/nginx.conf         Proxies /api to the API container
```

## Start the application

Docker, from the repository root:

```bash
docker compose up --build
```

Open http://localhost:8080.

Without Docker, two terminals:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
uvicorn app.main:app --port 8000
```

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The dev server proxies `/api` to port 8000.

Refresh the snapshot from Elexon. A complete January extract replaces `data/january_2026.json` only after every half-hour and forecast hour has been checked. An empty, partial, or conflicting pull leaves the previous file in place. The running API reads that file again when it changes, so the next request uses the new extract:

```bash
cd backend
source .venv/bin/activate
python -m app.ingest
```

Tests:

```bash
cd backend
source .venv/bin/activate
python -m pytest
```

## Hosted application

The image that gets hosted is the root `Dockerfile`. FastAPI serves `/api` and the built React app, and it listens on `$PORT`.

This machine is not logged in to Heroku, so there is no public URL yet. After `brew install heroku` and `heroku login`, from the repository root:

```bash
heroku create w4n8kq2m
heroku stack:set container --app w4n8kq2m
heroku container:push web --app w4n8kq2m
heroku container:release web --app w4n8kq2m
```

The app is then at `https://w4n8kq2m.herokuapp.com`. If that name is taken, run `heroku create` with no name and put the printed URL here.

## Tools

This application was built with Cursor, using the Grok model, for the Elexon ingest, the gate-time scoring, the API, the React desk, the tests, and the Docker setup.
