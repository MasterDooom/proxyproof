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
- [ ] Actual Android BLE advertising/scanning on physical phones
- [ ] Verified live Render deployment (requires linking the repository to your Render account)

## Deploy the backend (Render)

The repository includes [render.yaml](render.yaml), which creates a public HTTPS FastAPI service and a PostgreSQL datastore through a Render Blueprint.

1. Sign in or create an account at [Render](https://dashboard.render.com/).
2. Open [New Blueprint](https://dashboard.render.com/blueprints) and connect the GitHub repository `MasterDooom/proxyproof`.
3. Select branch `main` and review the resources in `render.yaml`.
4. When prompted for `PROXYPROOF_ORGANISER_INVITE_CODE`, enter a private invite code you choose and save it. Use that exact code when creating the organiser account in the app. Do not post it in GitHub or public chats.
5. Let Render create the web service and PostgreSQL database and wait for a successful deploy.
6. Open the service's public `onrender.com` URL, then append `/health`. It should return:
   `{"status":"ok","service":"proxyproof-api"}`
7. Open `/docs` on that same URL to inspect the API.

The API service and database are configured for the Singapore region, and the app uses the database's private connection string. The database URL is normalised to use the psycopg 3 driver.

### Important free-tier limits

The Blueprint uses free Render plans to avoid committing you to a bill. Free web services can spin down after 15 minutes of inactivity and take around a minute to wake up. Free Render Postgres databases expire 30 days after creation; upgrade the database before expiry to retain stored accounts and attendance. See [Render's free service limitations](https://render.com/docs/free). This is fine for a short demo, not durable production hosting.

## Point the Android app at Render

1. Install the latest APK from [Android APK workflow runs](https://github.com/MasterDooom/proxyproof/actions/workflows/android-apk.yml). Open the latest successful run and download artifact `proxyproof-debug-apk`; extract the ZIP to get `app-debug.apk`.
2. On the login/register screen, paste the public Render URL into **API server URL**, e.g. `https://proxyproof-api.onrender.com` (use the actual URL shown on your service).
3. Create an organiser account using the invite code you set during Blueprint creation, then create a room.
4. Sign out, create a student account, join that room, register the phone, then sign in as organiser again and test session/roster/manual attendance.

HTTPS means the phone can connect over Wi-Fi or mobile data; the laptop does not need to run the backend after Render is deployed.

## Build/download the APK

Every push to Android app files triggers the [Android APK workflow](https://github.com/MasterDooom/proxyproof/actions/workflows/android-apk.yml). The workflow builds and uploads an installable debug APK for 14 days.

## Local backend development (Windows)

From the repository root:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
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

The current Android APK includes login/register, room listing/joining, phone registration, organiser room creation and sessions, live session listing, manual roster updates, and student history. BLE scanning and advertising are not yet wired into the Android app, so attendance in the current APK is marked using the organiser's manual controls.

The rotating-token endpoint is ready for the next BLE integration. RSSI is a rough proximity heuristic and cannot prove that a student crossed the classroom door. Device binding is based on a random app-installation UUID, not hardware-backed attestation. Do not treat this prototype as production-grade attendance security.
