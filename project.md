# ProxyProof — Project Source of Truth

## 1. Objective

Build a working Android prototype in four days for BLE-assisted, room-specific attendance. A student should be marked present automatically when their registered room has an active session and their phone observes that room's valid BLE advertisement for long enough. Organisers can start/close sessions and inspect or correct attendance.

This is a prototype, not production-grade proof of physical presence. BLE RSSI is noisy and cannot reliably distinguish a person inside a room from someone immediately outside it. The demo must state this limitation honestly.

## 2. Product decisions

- Android-first: Kotlin + Jetpack Compose.
- One Android app supports Student and Organiser roles to keep the four-day scope achievable.
- Backend: FastAPI + SQLAlchemy; SQLite for local development/tests and PostgreSQL for hosted deployments. Keep schemas and storage semantics consistent across both.
- BLE: Android BLE advertiser on the organiser's phone; Android BLE scanner on student phones. Foreground operation first.
- No separate React dashboard in the four-day MVP. The organiser dashboard is an app screen. A web dashboard is a post-deadline enhancement.
- API polling for live attendance (about every 3–5 seconds while a session is open); avoid WebSockets until the core flow works.
- GitHub is the source of truth. Work in small, testable stages; do not generate a giant untested code dump.

## 2A. Implementation status — readiness branch

### Implemented in this branch

- FastAPI + SQLAlchemy data layer with SQLite local development and PostgreSQL/psycopg support.
- Student/organiser registration and login, PBKDF2 password hashing, 24-hour opaque bearer tokens stored as hashes, and role checks.
- Fail-closed hosted configuration: Render requires DATABASE_URL, PROXYPROOF_TOKEN_SECRET (at least 32 bytes), and PROXYPROOF_ORGANISER_INVITE_CODE (at least 16 bytes). Local development fallbacks are explicit.
- Room ownership and session ownership enforcement for organisers, while student access remains constrained by room enrolment.
- Versioned Alembic migrations to adopt the prior prototype schema without dropping its rows, then add session and room ownership. Migration tests cover fresh SQLite databases and legacy data preservation.
- Room creation/enrolment, device binding, session-specific BLE tag and rotating HMAC token APIs, automatic attendance validation, server-computed scheduled_start_at + 15 minutes cutoff, one-record-per-student/session integrity, manual correction, attendance history/percentage, roster and CSV export.
- Android Kotlin/Jetpack Compose app with student and organiser flows, editable API base URL, encrypted bearer-token storage using Android Keystore, debug-only HTTP configuration, and hosted HTTPS release default.
- Android foreground BLE advertiser/scanner components, shared 14-byte packet codec, 20-second server token rotation, repeated observations/dwell heuristic, ambiguity detection, permission handling, cancellation/cleanup, and clearly labelled manual fallback.
- Backend and Android GitHub Actions workflows. Backend CI passed 25 tests on 2026-10-13 (run: https://github.com/MasterDooom/proxyproof/actions/runs/38381048129). An Android build/unit-test workflow passed on 2026-10-13 for the code before the most recent foreground lifecycle change; the latest lifecycle change must pass a fresh CI run before release.
- Render service and PostgreSQL instance exist in the connected Render account, but DATABASE_URL is not yet configured for the service. No production data-persistence claim is made.

### Not yet verified or implemented

- End-to-end BLE operation on two physical Android phones. CI can validate packet-codec logic, not radio behaviour or device/OEM compatibility.
- Persistent hosted database connectivity, migration execution against Render PostgreSQL, and create/read/restart persistence smoke tests. These require securely setting DATABASE_URL in the Render service dashboard.
- Background BLE attendance; the initial design is explicitly foreground-only and stops BLE when the app leaves the foreground.
- Organiser-approved device replacement UI/endpoint, account recovery, rate limiting, and fully managed token revocation lifecycle.
- Production manufacturer identifier/protocol configuration. The current 0xFFFF manufacturer identifier is for development testing only and must be replaced before public distribution.
- Strong physical-presence proof. RSSI and rotating tokens do not stop all live relays, spoofing or attendance outside a classroom; device binding is an app-installation UUID, not hardware-backed attestation.
- Public-store release signing, durable production hosting/backup policy, and policy/privacy review.

## 3. Roles and core flows

### Organiser
1. Sign in using demo credentials or create an organiser account.
2. Create/select a room (building + room code/name, e.g. AB1-301) and subject.
3. Create a session with an explicit scheduled class start time. The automatic attendance cutoff is always scheduled start plus 15 minutes; it is not a duration counted from the organiser tapping Start.
4. App requests a fresh session token from the backend and advertises a compact payload over BLE.
5. View detected/marked students, manually add/remove attendance, and close the session.
6. View session history and export attendance as CSV.

### Student
1. Sign in and register this phone as the student's trusted device.
2. Join/select rooms they are enrolled in. In a real deployment, room enrolments should be assigned/approved by an organiser; the prototype may expose a controlled demo enrolment flow.
3. Keep the app's foreground attendance screen open during the demo.
4. Scan for active ProxyProof advertisements.
5. For a stable candidate, collect repeated observations over the dwell window; submit the six-byte session tag, latest rotating token and observed RSSI under the student's authenticated account. The server resolves the tag to the session.
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
      ├── Room/session owner checks + enrolments
      ├── Attendance sessions + rotating tokens
      ├── Attendance validation + cutoff enforcement
      └── History + CSV export
               │
               ▼
    SQLAlchemy models + local SQLite / hosted PostgreSQL

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
- `Room`: stable room ID, building, room code, display name and nullable organiser owner (nullable for migrated legacy rows).
- `RoomEnrollment`: user ID, room ID and enrollment time. For the prototype, students can self-enroll in rooms; real deployment should require organiser approval or roster provisioning.
- `AttendanceSession`: UUID, room ID, organiser owner, subject, scheduled start, calculated deadline, status and creation time.
- `SessionBleTag`: random 6-byte public session tag (12 hex characters).
- `AttendanceRecord`: session ID, student ID, device ID, marked time, method (`ble` or `manual`), reported RSSI and status. Unique constraint on `(session_id, student_id)`.

The BLE token is computed as a truncated HMAC of the session ID and the current 20-second time slot; it is not stored in the database. The server accepts the current or previous slot to tolerate a rotation boundary, but never accepts new automatic attendance after the session's 15-minute deadline. The Android packet codec places the six raw bytes of session tag followed by eight raw bytes of token in manufacturer data; the current `0xFFFF` identifier is development-only.

Store timestamps as UTC. SQLite stores naive UTC datetimes in this prototype; API responses convert them to timezone-aware UTC values.

## 8. API contract

Authentication:
- `POST /auth/register` — register student; organiser registration requires a local invite code.
- `POST /auth/login` — return opaque bearer token.
- `GET /auth/me` — current authenticated user
- `POST /auth/logout` — revoke the current bearer token.

Rooms and devices:
- `POST /devices/register` — bind a student to one app installation key.
- `GET /rooms` — list active rooms (authenticated).
- `POST /rooms` — create room (organiser).
- `POST /rooms/{room_id}/enroll` — student self-enrolls in a room (prototype flow).
- `GET /rooms/my` — student's enrolled rooms.

Sessions and attendance:
- `POST /sessions` — organiser starts a scheduled session; server computes deadline as scheduled start + 15 minutes.
- `GET /sessions/active` — list currently eligible sessions; student results are restricted to enrolled rooms and organisers see their own scheduled/live sessions
- `GET /sessions/my` — recent and historical sessions owned by the organiser.
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
