# ProxyProof — Project Source of Truth

## 1. Objective

Build a working Android prototype in four days for BLE-assisted, room-specific attendance. A student should be marked present automatically when their registered room has an active session and their phone observes that room's valid BLE advertisement for long enough. Organisers can start/close sessions and inspect or correct attendance.

This is a prototype, not production-grade proof of physical presence. BLE RSSI is noisy and cannot reliably distinguish a person inside a room from someone immediately outside it. The demo must state this limitation honestly.

## 2. Product decisions

- Android-first: Kotlin + Jetpack Compose.
- One Android app supports Student and Organiser roles to keep the four-day scope achievable.
- Backend: FastAPI + SQLite for the prototype. Keep persistence behind SQLAlchemy so SQLite can later be replaced with PostgreSQL.
- BLE: Android BLE advertiser on the organiser's phone; Android BLE scanner on student phones. Foreground operation first.
- No separate React dashboard in the four-day MVP. The organiser dashboard is an app screen. A web dashboard is a post-deadline enhancement.
- API polling for live attendance (about every 3–5 seconds while a session is open); avoid WebSockets until the core flow works.
- GitHub is the source of truth. Work in small, testable stages; do not generate a giant untested code dump.

## 3. Roles and core flows

### Organiser
1. Sign in using demo credentials or create an organiser account.
2. Create/select a room (building + room code/name, e.g. AB1-301) and subject.
3. Start a session for that room with a configurable duration (default 5 minutes).
4. App requests a fresh session token from the backend and advertises a compact payload over BLE.
5. View detected/marked students, manually add/remove attendance, and close the session.
6. View session history and export attendance as CSV.

### Student
1. Sign in and register this phone as the student's trusted device.
2. Join/select rooms they are enrolled in. In a real deployment, room enrolments should be assigned/approved by an organiser; the prototype may expose a controlled demo enrolment flow.
3. Keep the app's foreground attendance screen open during the demo.
4. Scan for active ProxyProof advertisements.
5. For an eligible room, collect repeated observations over a short dwell window; submit the session ID and latest rotating token with the authenticated student's identity.
6. Display a clear state: scanning, candidate detected, validating, present, ambiguous room, or session closed.
7. View attendance history and percentage.

## 4. Room matching and neighbouring-room behaviour

- Every room has a stable server-side room ID. Room names are display labels, never the security key.
- Every active attendance session has its own unguessable session ID, room ID, subject, start/end time and status.
- The BLE payload identifies a session and carries a compact short-lived token. Do not identify a room solely by RSSI or by whichever advertiser is strongest.
- The backend validates that the session is active, belongs to the requested room, the token is current, the student is enrolled in that room, the device is registered to that student, and the student has not already been marked for that session.
- Multiple rooms can advertise simultaneously. Scanner processes each candidate separately.
- If two eligible sessions are detected at similar RSSI (initial heuristic: within 8 dB) and both pass the dwell threshold, do not guess: show an ambiguous-room state and require the user to move closer to their classroom's beacon or choose the intended room for the prototype. Tune thresholds only after testing in actual rooms.
- The default demo rule is one attendance record per student per session, not one record per student globally.

## 5. Anti-proxy approach and limitations

MVP checks:
- Authenticated user and one registered device per student; device replacement requires organiser approval.
- Session-specific rotating token with a short validity window, verified by the server.
- Server-side checks for session status, room enrolment, expiry, duplicate submissions and device binding.
- Repeated BLE observations and a short continuous-presence/dwell requirement before submission.
- RSSI threshold used as a rough filter only; use configurable values and expose them for field testing.
- Organiser can manually correct a false negative/positive.

Limitations:
- BLE advertising data is observable to nearby scanners; a rotating token limits replay but is not a guarantee against live relay or device spoofing.
- RSSI is not a reliable distance or inside/outside detector. A student outside a wall may still pass. Do not claim the prototype makes proxy attendance impossible.
- Phone advertising support varies by device. Check BluetoothAdapter.isMultipleAdvertisementSupported / advertiser availability and handle unsupported devices. For a reliable real deployment, a fixed BLE beacon placed inside the room is preferable to relying on the organiser's phone.
- Start with the app open in foreground; background scanning/advertising and OEM battery restrictions are out of scope for the deadline.

## 6. Architecture

    Android app (Kotlin / Jetpack Compose)
      ├── Student UI
      ├── Organiser UI
      ├── BLE scanner + advertiser (foreground)
      ├── Repository / API client
      └── Local UI state
               │ HTTPS/JSON
               ▼
    FastAPI backend
      ├── Authentication + device binding
      ├── Rooms + enrolments
      ├── Attendance sessions + rotating tokens
      ├── Attendance validation
      └── History + CSV export
               │
               ▼
    SQLAlchemy models + SQLite database

Keep BLE platform code separate from Compose screens. Suggested Android packages:
- ui/auth
- ui/student
- ui/organiser
- ui/rooms
- data/api
- data/repository
- domain/model
- ble/scanner
- ble/advertiser
- ble/permissions

Suggested backend modules:
- app/main.py
- app/core/config.py
- app/core/security.py
- app/db/session.py
- app/models/
- app/schemas/
- app/api/auth.py
- app/api/rooms.py
- app/api/sessions.py
- app/api/attendance.py
- app/services/token_service.py
- app/services/attendance_service.py
- tests/

## 7. Data model

- User: id, display_name, email/username, password_hash, role.
- Device: id, user_id, device_fingerprint, approved_at, is_active. Enforce one active device per student in the prototype.
- Room: id, building, room_code, display_name, is_active.
- RoomEnrollment: user_id, room_id, subject_label, active. Unique (user_id, room_id, subject_label).
- AttendanceSession: id, room_id, subject_label, organiser_id, started_at, ends_at, status.
- AttendanceToken: session_id, token_hash or verifiable token metadata, valid_from, valid_until. Do not store raw long-lived secrets in client logs.
- AttendanceRecord: id, session_id, student_id, device_id, marked_at, method (ble or manual), rssi_at_mark, status. Unique (session_id, student_id).

Use UTC timestamps on the backend and format them locally in the app.

## 8. API contract (initial)

- POST /auth/register
- POST /auth/login
- POST /devices/register
- GET /rooms
- POST /rooms
- POST /rooms/{room_id}/enrollments
- GET /rooms/my
- POST /sessions — organiser starts a session
- POST /sessions/{session_id}/close
- GET /sessions/active
- GET /sessions/{session_id}/current-token — organiser app obtains the current short-lived token for BLE advertising
- POST /attendance/ble — submit session ID, token and measured RSSI
- POST /sessions/{session_id}/attendance/manual — organiser override
- GET /attendance/me
- GET /sessions/{session_id}/attendance
- GET /attendance/export.csv

All endpoints except registration/login must require authentication. Enforce role checks server-side; never trust a role supplied by the client. Treat client-reported RSSI as a heuristic, not a cryptographic security property.

## 9. Four-day implementation plan

### Day 1 — Scaffold and vertical slice
- Inspect repo and create a clear README.
- Scaffold Android app and FastAPI backend.
- Implement data models, SQLite setup and health endpoint.
- Build Compose navigation and Student/Organiser demo screens.
- Define API schemas and a documented local run workflow.
- Check in working, small increments.

### Day 2 — Rooms, sessions and BLE
- Implement room CRUD/enrolment and session start/close APIs.
- Add Android BLE permission requests for supported Android versions.
- Implement foreground advertising on organiser device and scanning on student device.
- Verify payload parsing with two physical Android phones.
- Keep a manual/demo fallback so the presentation is not blocked by unsupported BLE hardware.

### Day 3 — Attendance and dashboard
- Implement rotating-token verification and attendance submission.
- Add duplicate/session/enrolment/device checks.
- Connect UI to API; poll attendance during open sessions.
- Add history, percentages, manual overrides and CSV export.
- Test two simultaneous sessions in neighbouring rooms.

### Day 4 — Stabilise and demonstrate
- Test on real devices; handle Bluetooth disabled, permission denied, unsupported advertising and API unavailable.
- Add backend unit tests for token expiry, wrong room, wrong enrolment, duplicate attendance and closed sessions.
- Fix integration failures before adding new features.
- Write README setup instructions, known limitations, architecture diagram and a 2–3 minute demo script.
- Record a backup demo path using the manual attendance mode if BLE hardware fails.

## 10. Definition of Done

- App launches and Student/Organiser flows are navigable.
- Organiser can create a room and start/close a session.
- Two physical Android phones can demonstrate BLE discovery if both devices support the required roles.
- A valid, enrolled student can be marked once for the matching active room session.
- Wrong/expired tokens, closed sessions, unregistered devices and duplicate submissions are rejected.
- Two distinct room sessions do not share attendance records.
- Organiser can see the attendance list and manually correct it.
- Attendance history and CSV export work.
- README explains setup, test results and BLE limitations.
- No claim that BLE alone proves a person is inside a classroom.

## 11. Working rules

1. Read this file before making architectural changes.
2. Inspect the current repository before creating or replacing files.
3. Implement one vertical slice at a time and run the relevant checks after each stage.
4. Prefer simple, maintainable code over abstractions that do not help the MVP.
5. Never claim a build/test passed unless it was actually run.
6. Keep secrets and local environment files out of Git; provide .env.example.
7. Update this file when a deliberate scope or architecture decision changes.
