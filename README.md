# ProxyProof — Bluetooth Attendance

ProxyProof is an Android-first prototype for room-specific BLE-assisted attendance. The organiser starts a session for a room, and enrolled students can be marked automatically when their registered phone observes the room's short-lived BLE advertisement.

## Current implementation

- [x] Project scope, architecture and delivery rules in [project.md](project.md)
- [x] FastAPI + SQLite backend with room and session APIs
- [x] Student/organiser registration and login with bearer-token authentication
- [x] One registered installation ID per student account
- [x] Student room enrollment
- [x] Compact room-session BLE tag and 20-second HMAC token
- [x] Server-enforced 15-minute attendance window
- [x] Duplicate prevention, manual attendance correction, student history and CSV export
- [x] Backend API tests and GitHub Actions workflow (13 tests passing in CI as of 2026-10-13)
- [ ] Android Compose screens connected to API
- [ ] Android BLE advertisement/scanning integration
- [ ] Real-device end-to-end verification

## Run the backend on Windows

In CMD or PowerShell:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check: <http://127.0.0.1:8000/health>

Interactive API docs: <http://127.0.0.1:8000/docs>

Run backend tests in a separate terminal:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

## Local demo account setup

Use `POST /auth/register` to create a student account. Organiser registration requires the development invite code `local-demo-organiser-code` unless `PROXYPROOF_ORGANISER_INVITE_CODE` is set in the environment before starting the server.

Student example:

```json
{
  "username": "alice",
  "display_name": "Alice",
  "password": "correct-horse-123",
  "role": "student"
}
```

Organiser example:

```json
{
  "username": "teacher",
  "display_name": "Demo Organiser",
  "password": "correct-horse-123",
  "role": "organiser",
  "organiser_invite_code": "local-demo-organiser-code"
}
```

Register a student phone using `POST /devices/register` with a random per-installation `device_key` (the Android app will generate and retain a UUID). Enrol the student in a room with `POST /rooms/{room_id}/enroll`.

## Key attendance rule

Automatic attendance is accepted only from the scheduled class start through the next 15 minutes. For an 08:00 class, the server-side deadline is 08:15, even if the organiser starts the app late. The class continues; only the attendance window closes. The organiser can still make a clearly labelled manual correction.

The BLE payload uses a 6-byte random session tag and an 8-byte HMAC token that rotates every 20 seconds. The backend accepts the current or immediately previous token slot to tolerate a packet arriving at a rotation boundary. The separate 15-minute attendance deadline remains authoritative.

## API flow

1. Register/login as an organiser and use its bearer token to create a room.
2. Register/login as a student, register the student's installation key, and enrol them in the room.
3. Create a session with a timezone-aware `scheduled_start_at`.
4. On the organiser phone, poll `GET /sessions/{session_id}/current-token` and advertise the returned compact `session_tag` + `token`.
5. On the student phone, scan the BLE payload and submit `POST /attendance/ble` with `session_tag`, `token`, and observed `rssi`.
6. Use `GET /sessions/{session_id}/attendance` for the organiser roster, `GET /attendance/me` for student history, and `GET /attendance/export.csv?session_id=...` to export the session.

## Security limitations

This is a local prototype, not production-ready identity or attendance security. The development organiser invite code and token secret must be replaced before deployment; configure a long random `PROXYPROOF_TOKEN_SECRET` environment variable. Device binding uses an app-generated UUID and is not hardware-backed attestation. RSSI is client-reported and can be spoofed. BLE range cannot reliably distinguish a student inside a room from someone standing outside it. Do not expose this API publicly without HTTPS, secret management, rate limiting, stronger role provisioning and security review.
