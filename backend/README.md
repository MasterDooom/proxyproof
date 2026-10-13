# ProxyProof API

The backend currently supports authentication, room creation/listing, student room enrollment, one-device registration, scheduled attendance sessions, rotating BLE tokens, attendance validation, manual overrides, history and CSV export.

## Requirements

- Python 3.11 or newer
- Windows PowerShell/CMD, macOS, or Linux

## Run on Windows

From the repository root:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Using `python -m uvicorn` avoids Windows PATH issues with the `uvicorn.exe` launcher.

Open <http://127.0.0.1:8000/health> for the health check and <http://127.0.0.1:8000/docs> to try the APIs interactively.

Run tests in a second terminal:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

## Test workflow

1. Register an organiser using `POST /auth/register` with role `organiser` and the local invite code `local-demo-organiser-code`.
2. Authorize Swagger using the returned bearer token. Use this token to create a room and start a session.
3. Register a student account. Register the student's app installation key using `POST /devices/register`.
4. Enrol the student into a room via `POST /rooms/{room_id}/enroll`.
5. Create a session with an ISO-8601 `scheduled_start_at` including a timezone offset.
6. The organiser polls `GET /sessions/{session_id}/current-token`; the returned compact tag and token are what the organiser phone advertises over BLE.
7. The student app sends the observed tag, token and RSSI to `POST /attendance/ble`.
8. Inspect the organiser roster with `GET /sessions/{session_id}/attendance`, student history with `GET /attendance/me`, or download `GET /attendance/export.csv?session_id={session_id}`.

## Attendance deadline

The server calculates `attendance_deadline = scheduled_start_at + 15 minutes`. A class scheduled for 08:00 accepts automatic marks until 08:15, regardless of when the organiser opens the app. The server rejects BLE submissions after the deadline. Manual organiser corrections remain available.

The BLE token rotates every 20 seconds. The server accepts the current and previous slot only to tolerate requests crossing the rotation boundary; it never extends the 15-minute deadline.

## Environment variables

- `PROXYPROOF_TOKEN_SECRET`: long random secret used to compute BLE tokens. The default is for local development only.
- `PROXYPROOF_ORGANISER_INVITE_CODE`: invite code required to create organiser accounts. The default is for local development only.
- `PROXYPROOF_MIN_RSSI_DBM`: rough proximity threshold; default `-88` dBm.

Set environment variables before launching Uvicorn. This API has no deployment-grade secret loading by itself and is not safe to expose publicly as-is.
