# ProxyProof API

This is the first backend slice: health checks, room creation/listing, scheduled attendance sessions, and the server-side 15-minute attendance window.

## Requirements

- Python 3.11 or newer
- Windows PowerShell, CMD, macOS, or Linux

## Run on Windows (PowerShell)

From the repository root:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

If PowerShell blocks activation, run the virtual environment's interpreter directly:
```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open <http://127.0.0.1:8000/health> for the health check and <http://127.0.0.1:8000/docs> to try the API interactively.

## API sequence

1. `POST /rooms` with `{"building":"AB1","room_code":"301","display_name":"AB1-301"}`.
2. Copy the returned numeric room `id`.
3. `POST /sessions` with `{"room_id":1,"subject_label":"Engineering Mathematics","scheduled_start_at":"2026-10-11T16:00:00+05:30"}`. Use a real class start time; the example timestamp is illustrative.
4. `GET /sessions/active` returns sessions only when current server time is between the scheduled start and the 15-minute deadline.
5. `POST /sessions/{session_id}/close` closes the session early.

The 15-minute cutoff is calculated from `scheduled_start_at`, not from when the organiser happens to create the session. Timestamps must include a timezone offset.

## Current limitations

Authentication, enrolment/device binding, token rotation, BLE and attendance records are not implemented yet. Do not deploy this prototype API publicly; the next stages add access control and validated attendance.
