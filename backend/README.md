# ProxyProof API

FastAPI service with SQLite for local development and Render PostgreSQL for hosted prototypes.

## Local Windows setup

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:APP_ENV = "development"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check: <http://127.0.0.1:8000/health>

API explorer: <http://127.0.0.1:8000/docs>

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Hosted Render setup

The repository root contains `render.yaml`. Use **Render Dashboard → New → Blueprint**, connect `MasterDooom/proxyproof`, and select `main`.

The Blueprint defines:
- Free web service in Singapore running Uvicorn on Render's `$PORT`.
- Free Render Postgres database in Singapore.
- `DATABASE_URL` bound to the database's private `connectionString`.
- A generated `PROXYPROOF_TOKEN_SECRET`.
- A one-time prompted `PROXYPROOF_ORGANISER_INVITE_CODE`; set a private code and keep it to create your organiser account.

The existing hosted service is live at `https://proxyproof-api.onrender.com`. For immediate internal testing it currently uses `sqlite:///./proxyproof.db`; `/health` runs `SELECT 1` and returns `storage_backend` plus `storage_warning`. This SQLite file is on Render's temporary filesystem and is not durable. Before keeping real attendance records, set `DATABASE_URL` to the provisioned PostgreSQL **Internal Database URL** from the Render dashboard. Never commit or share that URL.

The database URL is normalised from Render's `postgresql://` format to `postgresql+psycopg://`; `psycopg[binary]` is installed from requirements. Local development defaults to SQLite. Hosted deployments refuse to start when `DATABASE_URL` is missing. The current explicit SQLite demo setting is a temporary exception for internal testing, not a persistent database. Hosted startup runs versioned Alembic migrations; the baseline adopts existing prototype tables without dropping them, and additive migrations add session and room ownership safely.

## API happy path

1. Register/log in as an organiser; save its bearer token.
2. Create a room using `POST /rooms`.
3. Register a student account; use `POST /devices/register` to bind a random app-installation UUID.
4. Enrol the student with `POST /rooms/{room_id}/enroll`.
5. Start a session with `POST /sessions` and a timezone-aware `scheduled_start_at`; organisers can review owned active and historical sessions with `GET /sessions/my`.
6. Organiser polls `GET /sessions/{session_id}/current-token`; the app should broadcast the returned six-byte session tag and 8-byte rotating HMAC token over BLE.
7. Student BLE scanner submits `POST /attendance/ble` with session tag, current token, and observed RSSI.
8. The organiser roster is `GET /sessions/{session_id}/attendance`; manual correction is `POST /sessions/{session_id}/attendance/manual`; student history is `GET /attendance/me`; CSV is `GET /attendance/export.csv?session_id=...`.

The readiness branch includes foreground BLE advertising/scanning and a development-only manufacturer-data identifier. Validate this on two physical Android devices before relying on BLE in class; manual organiser attendance remains the fallback. The development manufacturer ID must be replaced with a properly assigned/approved protocol identifier before public release.

## Attendance cutoff

The server computes `attendance_deadline = scheduled_start_at + 15 minutes`. For an 08:00 class, the deadline is 08:15, regardless of when the organiser opens the session. The class continues; only automatic attendance closes. Manual correction is available afterward.

## Free-tier limitations and security

Render free web services spin down after 15 minutes without traffic and can take around a minute to wake up. Render Free Postgres expires 30 days after creation; upgrade it before expiry to keep data. This setup is a temporary prototype, not production deployment.

The organiser invite code and BLE secret must remain private. Authentication uses opaque 24-hour bearer tokens, and `POST /auth/logout` revokes the current token. The service has process-local per-IP throttles for login, registration, and BLE submission/eligibility. Shared/distributed rate limiting across multiple service instances, account recovery, revocation of all sessions, organiser-approved device replacement, and hardware-backed device attestation are not yet implemented. Versioned Alembic migrations are included. RSSI is client-reported and cannot prove a person is inside a room.
