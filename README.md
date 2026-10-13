# ProxyProof — Bluetooth Attendance

ProxyProof is an Android-first prototype for room-specific BLE-assisted attendance. The organiser starts a session for a room and enrolled students can be marked once during the first 15 minutes of the scheduled class.

## Implemented

- [x] FastAPI backend with student/organiser accounts and role checks
- [x] PostgreSQL support for hosted deployment; SQLite for local development
- [x] Student device binding and room enrolment
- [x] Room/session isolation and a server-enforced 15-minute cutoff
- [x] Rotating BLE-token API and attendance validation endpoint
- [x] Attendance roster, manual correction, history, percentage and CSV export
- [x] Android Compose login/register and student/organiser screens
- [x] GitHub Actions workflows for backend tests and debug APK builds
- [x] Android foreground BLE advertiser/scanner and packet codec implemented (physical-phone validation still pending)
- [ ] Verified Render PostgreSQL connection and persistent-data round trip (requires setting `DATABASE_URL` for the existing service)

## Deploy the backend (Render)

The repository includes [render.yaml](render.yaml), which defines a public HTTPS FastAPI service and PostgreSQL datastore through a Render Blueprint. The current existing Render web service was created separately; its `DATABASE_URL` must be added in the dashboard before this hardened branch can be deployed.

1. Open the existing service at [Render Dashboard](https://dashboard.render.com/web/srv-db6vnvcs728c73cv8ihg) and the database at [proxyproof-postgres](https://dashboard.render.com/d/dpg-db6vnfek1f9s73bo4f8g-a).
2. In the PostgreSQL page, open **Connect** and copy the **Internal Database URL**. Do not expose it in GitHub, screenshots, or chat.
3. In the web service's **Environment** settings, set `DATABASE_URL` to that internal URL. Keep the existing `PROXYPROOF_TOKEN_SECRET` and `PROXYPROOF_ORGANISER_INVITE_CODE` private and strong.
4. Update the service start command to `cd backend && alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`; keep its build command `cd backend && pip install -r requirements.txt`.
5. Only deploy this hardened branch after its checks pass and the environment variables above are configured. The application now refuses to start in Render without a database URL rather than silently using ephemeral SQLite.
6. Test the public `/health` endpoint after deployment. It executes `SELECT 1` against the configured database and should return `{"status":"ok","service":"proxyproof-api"}`.
7. Open `/docs` to inspect the API. For a completely new Render environment, use **New Blueprint** and follow `render.yaml` instead of manually creating duplicate resources.

The intended API/database region is Singapore. The app normalises Render's PostgreSQL URL to the psycopg 3 driver. The hosted database connection is not considered verified until `/health`, a create/read smoke test, and a restart persistence test all pass.

### Important free-tier limits

The Blueprint uses free Render plans to avoid committing you to a bill. Free web services can spin down after 15 minutes of inactivity and take around a minute to wake up. Free Render Postgres databases expire 30 days after creation; upgrade the database before expiry to retain stored accounts and attendance. See [Render's free service limitations](https://render.com/docs/free). This is fine for a short demo, not durable production hosting.

## Point the Android app at Render

1. Install the latest APK from [Android APK workflow runs](https://github.com/MasterDooom/proxyproof/actions/workflows/android-apk.yml). Open the latest successful run and download artifact `proxyproof-debug-apk`; extract the ZIP to get `app-debug.apk`.
2. On the login/register screen, paste the public Render URL into **API server URL**, e.g. `https://proxyproof-api.onrender.com` (use the actual URL shown on your service).
3. Create an organiser account using the invite code you set during Blueprint creation, then create a room.
4. Sign out, create a student account, join that room, register the phone, then sign in as organiser again and test session/roster/manual attendance.
5. For automatic attendance, keep the organiser's session screen in the foreground and start BLE broadcast; on a second phone, open student attendance scanning. Grant nearby-device permissions and verify the server confirms the record. If the phone does not support BLE advertising, use manual organiser attendance as a labelled fallback.

HTTPS means the phone can connect over Wi-Fi or mobile data; the laptop does not need to run the backend after Render is deployed.

## Build/download the APK

Every push to Android app files triggers the [Android APK workflow](https://github.com/MasterDooom/proxyproof/actions/workflows/android-apk.yml). The workflow builds and uploads an installable debug APK for 14 days.

## Local backend development (Windows)

From the repository root:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:APP_ENV = "development"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Check <http://127.0.0.1:8000/health> and <http://127.0.0.1:8000/docs>.

Run tests in a second terminal:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Local development uses SQLite unless `DATABASE_URL` is set. Render uses Postgres via `DATABASE_URL`.

## Current functional scope and limitations

The readiness branch adds foreground BLE advertising and scanning, a shared 14-byte packet codec, token refresh, repeated-observation/dwell checks, ambiguous-room messaging, and server-side submission. A GitHub Actions build succeeded for the current BLE/Keystore code, but physical two-phone BLE validation is still outstanding. Keep the app in the foreground; background attendance is not claimed.

The rotating-token endpoint feeds the Android BLE advertiser. The current development BLE manufacturer identifier (`0xFFFF`) is explicitly not suitable for public release; replace it with an appropriate assigned/approved identifier. RSSI is only a rough proximity heuristic and cannot prove that a student crossed the classroom door. Device binding uses a random app-installation UUID, not hardware-backed attestation. Room/session organiser ownership and fail-closed production configuration have been added on the readiness branch, with Alembic migrations that are covered by CI. Rate limiting, account recovery, durable production hosting and physical BLE validation remain release gates.
