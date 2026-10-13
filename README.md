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

The API is deployed at [https://proxyproof-api.onrender.com](https://proxyproof-api.onrender.com). The current hosted instance is configured with `DATABASE_URL=sqlite:///./proxyproof.db` as a temporary internal-test datastore because the private Render PostgreSQL connection URL was not available to the deployment integration. **SQLite on Render's temporary filesystem is not durable. Accounts, enrolments, sessions, and attendance may be lost on restart or redeploy. Do not use this configuration for official attendance records.** The login screen's connection test and `/health` response disclose this warning.

### Switch the hosted demo to durable PostgreSQL

1. Open the existing service at [Render Dashboard](https://dashboard.render.com/web/srv-db6vnvcs728c73cv8ihg) and the provisioned database at [proxyproof-postgres](https://dashboard.render.com/d/dpg-db6vnfek1f9s73bo4f8g-a).
2. In the PostgreSQL page, open **Connect** and copy the **Internal Database URL**. Do not expose it in GitHub, screenshots, or chat.
3. In the web service's **Environment** settings, replace `DATABASE_URL` with that internal URL. Keep `PROXYPROOF_TOKEN_SECRET` and `PROXYPROOF_ORGANISER_INVITE_CODE` private and strong.
4. The current app applies Alembic migrations on hosted startup. The Blueprint's start command also applies migrations before Uvicorn, which is safe because the migrations are versioned.
5. After the restart, check `/health` shows `storage_backend: "postgresql"` and an empty `storage_warning`. Then run create/read and restart-persistence tests before storing real attendance records.
6. Open `/docs` to inspect the API. For a brand-new environment, use **New Blueprint** and follow `render.yaml` instead of manually creating duplicate resources.

The intended API/database region is Singapore. The app normalises Render's PostgreSQL URL to the psycopg 3 driver. The current service is healthy, but durable Postgres connectivity has not been verified until the change above and its persistence checks pass.

### Important free-tier limits

The Blueprint uses free Render plans to avoid committing you to a bill. Free web services can spin down after 15 minutes of inactivity and take around a minute to wake up. Free Render Postgres databases expire 30 days after creation; upgrade the database before expiry to retain stored accounts and attendance. See [Render's free service limitations](https://render.com/docs/free). This is fine for a short demo, not durable production hosting.

See [PRIVACY.md](PRIVACY.md) for the data collected, permissions, retention limitations and prototype presence-verification limits.

## Point the Android app at Render

1. Install the latest APK from [Android APK workflow runs](https://github.com/MasterDooom/proxyproof/actions/workflows/android-apk.yml). Open the latest successful run and download artifact `proxyproof-debug-apk`; extract the ZIP to get `app-debug.apk`.
2. On the login/register screen, paste the public Render URL into **API server URL**, e.g. `https://proxyproof-api.onrender.com` (use the actual URL shown on your service).
3. Create an organiser account using the invite code you set during Blueprint creation, then create a room.
4. Sign out, create a student account, join that room, register the phone, then sign in as organiser again and test session/roster/manual attendance, session history, and CSV export.
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

The readiness branch adds foreground BLE advertising and scanning, a shared 14-byte packet codec, token refresh, scheduled broadcast arming, cutoff shutdown, repeated-observation/dwell checks, ambiguous-room messaging, server-side eligibility checks, organiser-owned session history, and a system file-picker flow for saving CSV exports. The latest CI run passed 31 backend tests and built the debug APK; physical two-phone BLE validation is still outstanding. Keep the app in the foreground; background attendance is not claimed.

The rotating-token endpoint feeds the Android BLE advertiser. The current development BLE manufacturer identifier (`0xFFFF`) is explicitly not suitable for public release; replace it with an appropriate assigned/approved identifier. RSSI is only a rough proximity heuristic and cannot prove that a student crossed the classroom door. Device binding uses a random app-installation UUID, not hardware-backed attestation. Room/session organiser ownership and fail-closed production configuration have been added on the readiness branch, with Alembic migrations that are covered by CI. Rate limiting, account recovery, durable production hosting and physical BLE validation remain release gates.
