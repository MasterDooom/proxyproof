# ProxyProof — Bluetooth Attendance

ProxyProof is an Android-first prototype for room-specific BLE-assisted attendance. Organisers create room sessions; students register their phone and join rooms. BLE advertiser/scanner integration is the next stage.

## Implemented

- [x] Scope and architecture in [project.md](project.md)
- [x] FastAPI + SQLite backend with authentication and role checks
- [x] One app-installation device key per student account
- [x] Room creation/listing and student room enrolment
- [x] Scheduled sessions with a server-enforced 15-minute attendance window
- [x] Rotating compact BLE tokens and server-side BLE attendance endpoint
- [x] Duplicate rejection, manual attendance correction, history, percentage and CSV export
- [x] Backend tests: 13 passed in CI
- [x] Android Jetpack Compose login/register and student/organiser screens
- [x] Android APK build workflow
- [ ] Actual Android BLE advertising/scanning
- [ ] Real-device BLE end-to-end verification

## Build/download the APK

GitHub Actions builds an installable **debug APK** on Android-source pushes.

1. Open [Android APK workflow runs](https://github.com/MasterDooom/proxyproof/actions/workflows/android-apk.yml).
2. Open the latest run with a green check.
3. At the bottom, under **Artifacts**, download `proxyproof-debug-apk`.
4. Extract the ZIP to get `app-debug.apk`, transfer it to your Android phone, and install it. Android may ask you to allow installing apps from that source.

The APK is a development build; BLE scanning/advertising is not enabled yet.

## Run the backend on Windows

From the repository root:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check: <http://127.0.0.1:8000/health>

Interactive API docs: <http://127.0.0.1:8000/docs>

Run tests in a second terminal:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

## Connecting the phone to your laptop

1. Keep the backend running with `--host 0.0.0.0`.
2. Put the phone and laptop on the same Wi-Fi network.
3. Run `ipconfig` on Windows and find the laptop's IPv4 address for the active Wi-Fi adapter.
4. In the app's Server URL field, enter `http://YOUR_LAPTOP_IPV4:8000`, e.g. `http://192.168.1.20:8000`.
5. If the phone cannot connect, allow Python/Uvicorn through Windows Defender Firewall on private networks.
6. Use the health route from the phone browser first: `http://YOUR_LAPTOP_IPV4:8000/health`.

The default `http://10.0.2.2:8000` URL is for Android emulator networking, not physical phones.

## Demo accounts

Register a student with `POST /auth/register`. To register an organiser, include the local invite code `local-demo-organiser-code`. Replace these defaults before any deployment.

## Attendance deadline

Automatic attendance is accepted from the scheduled class start through the next 15 minutes. An 08:00 class deadline is 08:15, irrespective of when the organiser opens the app. The class itself continues after that cutoff; only attendance submission closes.

## Security limitations

This is a local prototype, not production-ready attendance security. The development organiser invite code and token secret must be replaced before deployment. Device binding uses an app-generated UUID and is not hardware-backed. RSSI is client-reported and cannot reliably establish whether someone is inside a classroom rather than outside the wall.
