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

## 2A. Implementation status as of 2026-10-13

Implemented in the repository:
- FastAPI + SQLAlchemy + SQLite backend.
- Student/organiser registration and login, PBKDF2 password hashing, 24-hour opaque bearer tokens stored as hashes, and role checks.
- Single installation-key binding per student account.
- Room creation/listing and student self-enrollment for the prototype.
- Scheduled session creation with a server-computed 15-minute attendance deadline.
- Random 6-byte per-session BLE tag plus an HMAC-derived 8-byte token rotating every 20 seconds.
- BLE attendance submission validation: active session, deadline, room enrollment, registered device, current/previous token slot, rough RSSI threshold and one record per student/session.
- Manual organiser corrections, student attendance history/percentage, organiser roster and session CSV export.
- API tests and GitHub Actions workflow; 13 tests passed in CI on 2026-10-13 (run: https://github.com/MasterDooom/proxyproof/actions/runs/38371533680).

Implemented after the backend milestone:
- Android Jetpack Compose app with login/register, editable API URL, student dashboard, room enrolment, one-installation registration, history/percentage, organiser room creation, session controls, roster, and manual attendance correction.
- Android debug APK builds in GitHub Actions. Verified successful build on 2026-10-13 (run: https://github.com/MasterDooom/proxyproof/actions/runs/38373408341); artifact name `proxyproof-debug-apk`.
- Android target SDK 36 and minimum SDK 26 for a stable prototype build.

Not yet implemented:
- Android BLE advertising/scanning and real-device discovery/submission.
- A real device-change approval UI/endpoint (mismatched device keys are rejected).
- Production-grade authentication/authorisation, hardware-backed device attestation or robust inside-room proof.

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


## 3A. Attendance cutoff and late arrivals

- Each class/session has a scheduled class start time, separate from when the organiser opens the session.
- Automatic attendance is allowed only from the scheduled start time through the 15-minute grace window.
- The backend computes and enforces `attendance_deadline = scheduled_start_at + 15 minutes`; client clocks and delayed requests cannot extend it.
- Example: an 08:00 class accepts automatic attendance until 08:15. After 08:15, reject all new automatic BLE attendance submissions even if the session's BLE signal remains visible.
- The organiser may still view the roster and make a clearly logged manual correction after the deadline.
- The class itself continues after the attendance window closes. BLE advertising/scanning for attendance should stop at the deadline.
- If an organiser starts the attendance session late, do not reset the deadline to 15 minutes after opening. Use the scheduled class start time. If the scheduled start time is missing, require the organiser to enter/confirm it before starting.

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

- `User`: ID, username, display name, PBKDF2 password hash, role and active flag.
- `ApiToken`: SHA-256 hash of an opaque bearer token, user ID, expiry and creation time. Raw access tokens are returned once and not persisted.
- `Device`: user ID, app-generated installation UUID, active flag and registration time. The current prototype permits one installation per student but does not provide device replacement approval yet.
- `Room`: stable room ID, building, room code and display name.
- `RoomEnrollment`: user ID, room ID and enrollment time. For the prototype, students can self-enroll in rooms; real deployment should require organiser approval or roster provisioning.
- `AttendanceSession`: UUID, room ID, subject, scheduled start, calculated deadline, status and creation time.
- `SessionBleTag`: random 6-byte public session tag (12 hex characters).
- `AttendanceRecord`: session ID, student ID, device ID, marked time, method (`ble` or `manual`), reported RSSI and status. Unique constraint on `(session_id, student_id)`.

The BLE token is computed as a truncated HMAC of the session ID and the current 20-second time slot; it is not stored in the database. The server accepts the current or previous slot to tolerate a rotation boundary, but never accepts new automatic attendance after the session's 15-minute deadline.

Store timestamps as UTC. SQLite stores naive UTC datetimes in this prototype; API responses convert them to timezone-aware UTC values.

## 8. API contract

Authentication:
- `POST /auth/register` — register student; organiser registration requires a local invite code.
- `POST /auth/login` — return opaque bearer token.
- `GET /auth/me` — current authenticated user.

Rooms and devices:
- `POST /devices/register` — bind a student to one app installation key.
- `GET /rooms` — list active rooms (authenticated).
- `POST /rooms` — create room (organiser).
- `POST /rooms/{room_id}/enroll` — student self-enrolls in a room (prototype flow).
- `GET /rooms/my` — student's enrolled rooms.

Sessions and attendance:
- `POST /sessions` — organiser starts a scheduled session; server computes deadline as scheduled start + 15 minutes.
- `GET /sessions/active` — list currently eligible sessions; student results are restricted to enrolled rooms.
- `GET /sessions/{session_id}` — session detail.
- `GET /sessions/{session_id}/current-token` — organiser gets compact BLE session tag and current rotating token.
- `POST /sessions/{session_id}/close` — organiser closes session early.
- `POST /attendance/ble` — student submits session tag, token and observed RSSI.
- `GET /sessions/{session_id}/attendance` — organiser roster with attendance.
- `POST /sessions/{session_id}/attendance/manual` — organiser manual correction.
- `GET /attendance/me` — student history and percentage.
- `GET /attendance/export.csv?session_id=...` — organiser CSV export.

All endpoints except health and register/login require bearer authentication. Organiser-only operations use server-side role checks. The RSSI value is reported by the client and is not a cryptographic security property. Do not expose the prototype API publicly.

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
