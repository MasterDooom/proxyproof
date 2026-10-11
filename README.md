# ProxyProof — Bluetooth Attendance

ProxyProof is an Android-first prototype for room-specific, BLE-assisted attendance. The goal is to demonstrate automatic attendance in the correct room while reducing casual proxy attendance.

## Project status

- [x] Product requirements and architecture recorded in [project.md](project.md)
- [x] First FastAPI backend slice: health, rooms, scheduled sessions and 15-minute deadline
- [ ] Android Compose app scaffold
- [ ] BLE advertiser/scanner integration
- [ ] Rotating tokens, device binding and enrolment validation
- [ ] Attendance records, live organiser view, history and CSV export

## Start the backend

Follow [backend/README.md](backend/README.md).

From the repository root on Windows PowerShell:

```powershell
cd backend
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open <http://127.0.0.1:8000/health> for the health check and <http://127.0.0.1:8000/docs> to try the API interactively.

## First API workflow

1. Create a room with `POST /rooms`, for example:
   `{"building":"AB1","room_code":"301","display_name":"AB1-301"}`
2. Copy the returned numeric room `id`.
3. Create a session with `POST /sessions` and a timezone-aware `scheduled_start_at`, for example:
   `{"room_id":1,"subject_label":"Engineering Mathematics","scheduled_start_at":"2026-10-12T08:00:00+05:30"}`
4. Use `GET /sessions/active` to see sessions inside their attendance window.
5. Use `POST /sessions/{session_id}/close` to close a session early.

## Attendance cutoff

Automatic attendance is only eligible from the scheduled class start through the next 15 minutes. For an 08:00 class, the server-side deadline is 08:15. The class itself continues; only the attendance window closes. Creating a session late does not reset this deadline.

## Security note

The current API slice is for local development only and has no authentication yet. Do not expose it to the public internet. BLE signal strength does not prove that someone is physically inside a room; RSSI is only a rough proximity heuristic.
