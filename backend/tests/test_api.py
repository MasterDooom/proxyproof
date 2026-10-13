from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db, normalize_database_url
from app.main import app
from app.models import AttendanceSession, User

test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def register_user(
    client: TestClient,
    username: str,
    role: str = "student",
    password: str = "correct-horse-123",
) -> dict:
    payload = {
        "username": username,
        "display_name": username.title(),
        "password": password,
        "role": role,
    }
    if role == "organiser":
        payload["organiser_invite_code"] = "local-demo-organiser-code"
    response = client.post("/auth/register", json=payload)
    assert response.status_code == 201, response.text
    data = response.json()
    return {
        "user": data["user"],
        "token": data["access_token"],
        "headers": {"Authorization": f"Bearer {data['access_token']}"},
    }


def create_room(client: TestClient, organiser: dict, room_code: str = "301") -> int:
    response = client.post(
        "/rooms",
        headers=organiser["headers"],
        json={
            "building": "AB1",
            "room_code": room_code,
            "display_name": f"AB1-{room_code}",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def enroll(client: TestClient, student: dict, room_id: int):
    response = client.post(
        f"/rooms/{room_id}/enroll",
        headers=student["headers"],
    )
    assert response.status_code == 200, response.text
    return response.json()


def register_device(client: TestClient, student: dict, device_key: str = "test-device-123456"):
    response = client.post(
        "/devices/register",
        headers=student["headers"],
        json={"device_key": device_key},
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_session(client: TestClient, organiser: dict, room_id: int, start_offset_minutes: int = -2, subject: str = "Engineering Mathematics"):
    scheduled_start = datetime.now(timezone.utc) + timedelta(minutes=start_offset_minutes)
    response = client.post(
        "/sessions",
        headers=organiser["headers"],
        json={
            "room_id": room_id,
            "subject_label": subject,
            "scheduled_start_at": scheduled_start.isoformat(),
        },
    )
    return response


def get_ble_advertisement(client: TestClient, organiser: dict, session_id: str):
    response = client.get(
        f"/sessions/{session_id}/current-token",
        headers=organiser["headers"],
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "proxyproof-api"}


def test_room_endpoints_require_authentication(client: TestClient):
    assert client.get("/rooms").status_code == 401
    assert client.post(
        "/rooms",
        json={"building": "AB1", "room_code": "301", "display_name": "AB1-301"},
    ).status_code == 401


def test_registration_login_and_organiser_invite(client: TestClient):
    denied = client.post(
        "/auth/register",
        json={
            "username": "fakeorganiser",
            "display_name": "Fake Organiser",
            "password": "correct-horse-123",
            "role": "organiser",
            "organiser_invite_code": "wrong",
        },
    )
    assert denied.status_code == 403

    student = register_user(client, "alice")
    login = client.post(
        "/auth/login",
        json={"username": "ALICE", "password": "correct-horse-123"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["username"] == "alice"
    assert client.get("/auth/me", headers=student["headers"]).json()["role"] == "student"

    bad_login = client.post(
        "/auth/login",
        json={"username": "alice", "password": "wrong-password"},
    )
    assert bad_login.status_code == 401


def test_student_cannot_create_room_and_duplicate_room_is_rejected(client: TestClient):
    student = register_user(client, "alice")
    organiser = register_user(client, "teacher", role="organiser")

    forbidden = client.post(
        "/rooms",
        headers=student["headers"],
        json={"building": "AB1", "room_code": "301", "display_name": "AB1-301"},
    )
    assert forbidden.status_code == 403

    create_room(client, organiser)
    duplicate = client.post(
        "/rooms",
        headers=organiser["headers"],
        json={"building": "AB1", "room_code": "301", "display_name": "Duplicate"},
    )
    assert duplicate.status_code == 409


def test_student_device_is_bound_to_one_installation(client: TestClient):
    student = register_user(client, "alice")
    register_device(client, student)
    duplicate_same_device = client.post(
        "/devices/register",
        headers=student["headers"],
        json={"device_key": "test-device-123456"},
    )
    assert duplicate_same_device.status_code == 201
    other_device = client.post(
        "/devices/register",
        headers=student["headers"],
        json={"device_key": "different-device-654321"},
    )
    assert other_device.status_code == 409


def test_valid_ble_attendance_and_duplicate_rejection(client: TestClient):
    student = register_user(client, "alice")
    organiser = register_user(client, "teacher", role="organiser")
    room_id = create_room(client, organiser)
    enroll(client, student, room_id)
    register_device(client, student)
    created = create_session(client, organiser, room_id)
    assert created.status_code == 201, created.text
    session = created.json()

    advertisement = get_ble_advertisement(client, organiser, session["id"])
    payload = {
        "session_tag": advertisement["session_tag"],
        "token": advertisement["token"],
        "rssi": -55,
    }
    marked = client.post("/attendance/ble", headers=student["headers"], json=payload)
    assert marked.status_code == 200, marked.text
    assert marked.json()["status"] == "present"
    assert marked.json()["session_id"] == session["id"]

    duplicate = client.post("/attendance/ble", headers=student["headers"], json=payload)
    assert duplicate.status_code == 409

    history = client.get("/attendance/me", headers=student["headers"])
    assert history.status_code == 200
    assert len(history.json()["items"]) == 1
    assert history.json()["items"][0]["status"] == "present"


def test_wrong_room_or_missing_device_is_rejected(client: TestClient):
    student = register_user(client, "alice")
    organiser = register_user(client, "teacher", role="organiser")
    room_id = create_room(client, organiser)
    session = create_session(client, organiser, room_id).json()
    advertisement = get_ble_advertisement(client, organiser, session["id"])

    # The student has no room enrolment and no registered phone.
    no_enrollment = client.post(
        "/attendance/ble",
        headers=student["headers"],
        json={
            "session_tag": advertisement["session_tag"],
            "token": advertisement["token"],
            "rssi": -50,
        },
    )
    assert no_enrollment.status_code == 409  # device registration is checked first

    register_device(client, student)
    wrong_room = client.post(
        "/attendance/ble",
        headers=student["headers"],
        json={
            "session_tag": advertisement["session_tag"],
            "token": advertisement["token"],
            "rssi": -50,
        },
    )
    assert wrong_room.status_code == 403


def test_weak_signal_and_invalid_token_are_rejected(client: TestClient):
    student = register_user(client, "alice")
    organiser = register_user(client, "teacher", role="organiser")
    room_id = create_room(client, organiser)
    enroll(client, student, room_id)
    register_device(client, student)
    session = create_session(client, organiser, room_id).json()
    advertisement = get_ble_advertisement(client, organiser, session["id"])

    invalid = client.post(
        "/attendance/ble",
        headers=student["headers"],
        json={"session_tag": advertisement["session_tag"], "token": "0" * 16, "rssi": -50},
    )
    assert invalid.status_code == 401

    weak = client.post(
        "/attendance/ble",
        headers=student["headers"],
        json={
            "session_tag": advertisement["session_tag"],
            "token": advertisement["token"],
            "rssi": -110,
        },
    )
    assert weak.status_code == 422


def test_fifteen_minute_cutoff_is_enforced(client: TestClient):
    organiser = register_user(client, "teacher", role="organiser")
    room_id = create_room(client, organiser)
    too_late = create_session(client, organiser, room_id, start_offset_minutes=-20)
    assert too_late.status_code == 422
    assert "window" in too_late.json()["detail"].lower()


def test_simultaneous_room_sessions_remain_separate(client: TestClient):
    student = register_user(client, "alice")
    organiser = register_user(client, "teacher", role="organiser")
    room_one = create_room(client, organiser, "301")
    room_two = create_room(client, organiser, "302")
    enroll(client, student, room_one)
    register_device(client, student)

    session_one = create_session(client, organiser, room_one, subject="Math").json()
    session_two = create_session(client, organiser, room_two, subject="Physics").json()
    ad_one = get_ble_advertisement(client, organiser, session_one["id"])
    ad_two = get_ble_advertisement(client, organiser, session_two["id"])
    assert ad_one["session_tag"] != ad_two["session_tag"]

    active = client.get("/sessions/active", headers=student["headers"])
    assert active.status_code == 200
    assert [item["id"] for item in active.json()] == [session_one["id"]]

    marked = client.post(
        "/attendance/ble",
        headers=student["headers"],
        json={
            "session_tag": ad_one["session_tag"],
            "token": ad_one["token"],
            "rssi": -55,
        },
    )
    assert marked.status_code == 200
    wrong_room = client.post(
        "/attendance/ble",
        headers=student["headers"],
        json={
            "session_tag": ad_two["session_tag"],
            "token": ad_two["token"],
            "rssi": -45,
        },
    )
    assert wrong_room.status_code == 403


def test_manual_attendance_roster_and_csv(client: TestClient):
    student = register_user(client, "alice")
    organiser = register_user(client, "teacher", role="organiser")
    room_id = create_room(client, organiser)
    enroll(client, student, room_id)
    session = create_session(client, organiser, room_id).json()

    manual = client.post(
        f"/sessions/{session['id']}/attendance/manual",
        headers=organiser["headers"],
        json={"student_id": student["user"]["id"], "status": "present"},
    )
    assert manual.status_code == 200, manual.text
    assert manual.json()["method"] == "manual"

    roster = client.get(
        f"/sessions/{session['id']}/attendance",
        headers=organiser["headers"],
    )
    assert roster.status_code == 200
    assert roster.json()["present_count"] == 1

    export = client.get(
        "/attendance/export.csv",
        headers=organiser["headers"],
        params={"session_id": session["id"]},
    )
    assert export.status_code == 200
    assert "alice" in export.text
    assert "present" in export.text


def test_closed_session_rejects_ble_attendance(client: TestClient):
    student = register_user(client, "alice")
    organiser = register_user(client, "teacher", role="organiser")
    room_id = create_room(client, organiser)
    enroll(client, student, room_id)
    register_device(client, student)
    session = create_session(client, organiser, room_id).json()
    ad = get_ble_advertisement(client, organiser, session["id"])
    closed = client.post(f"/sessions/{session['id']}/close", headers=organiser["headers"])
    assert closed.status_code == 200

    attendance = client.post(
        "/attendance/ble",
        headers=student["headers"],
        json={"session_tag": ad["session_tag"], "token": ad["token"], "rssi": -55},
    )
    assert attendance.status_code == 409


def test_submission_is_rejected_after_the_15_minute_deadline(client: TestClient):
    student = register_user(client, "alice")
    organiser = register_user(client, "teacher", role="organiser")
    room_id = create_room(client, organiser)
    enroll(client, student, room_id)
    register_device(client, student)
    session = create_session(client, organiser, room_id).json()
    ad = get_ble_advertisement(client, organiser, session["id"])

    # Simulate the clock passing the cutoff without waiting 15 minutes in a test.
    db = TestSessionLocal()
    try:
        row = db.get(AttendanceSession, session["id"])
        row.attendance_deadline = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        db.commit()
    finally:
        db.close()

    response = client.post(
        "/attendance/ble",
        headers=student["headers"],
        json={"session_tag": ad["session_tag"], "token": ad["token"], "rssi": -55},
    )
    assert response.status_code == 422
    assert "window" in response.json()["detail"].lower()



def test_database_url_normalizes_render_postgres_schemes():
    assert normalize_database_url(
        "postgresql://user:pass@host:5432/db"
    ) == "postgresql+psycopg://user:pass@host:5432/db"
    assert normalize_database_url(
        "postgres://user:pass@host:5432/db"
    ) == "postgresql+psycopg://user:pass@host:5432/db"
    assert normalize_database_url("sqlite:///./proxyproof.db") == "sqlite:///./proxyproof.db"

def test_organiser_can_only_manage_their_own_sessions(client: TestClient):
    owner = register_user(client, "owner_teacher", role="organiser")
    other = register_user(client, "other_teacher", role="organiser")
    room_id = create_room(client, owner, "401")
    response = create_session(client, owner, room_id)
    assert response.status_code == 201, response.text
    session_id = response.json()["id"]

    assert client.get(
        f"/sessions/{session_id}",
        headers=owner["headers"],
    ).status_code == 200
    assert client.get(
        f"/sessions/{session_id}/current-token",
        headers=owner["headers"],
    ).status_code == 200

    assert client.get(
        "/sessions/active",
        headers=other["headers"],
    ).json() == []
    assert client.get(
        f"/sessions/{session_id}",
        headers=other["headers"],
    ).status_code == 403
    assert client.get(
        f"/sessions/{session_id}/current-token",
        headers=other["headers"],
    ).status_code == 403
    assert client.get(
        f"/sessions/{session_id}/attendance",
        headers=other["headers"],
    ).status_code == 403
    assert client.post(
        f"/sessions/{session_id}/close",
        headers=other["headers"],
    ).status_code == 403
    assert client.get(
        "/attendance/export.csv",
        params={"session_id": session_id},
        headers=other["headers"],
    ).status_code == 403

    assert client.post(
        f"/sessions/{session_id}/close",
        headers=owner["headers"],
    ).status_code == 200

def test_organisers_cannot_create_sessions_for_another_organisers_room(client: TestClient):
    first = register_user(client, "first_organiser", role="organiser")
    second = register_user(client, "second_organiser", role="organiser")
    first_room_id = create_room(client, first, "501")
    second_room_id = create_room(client, second, "502")

    first_rooms = {
        row["id"] for row in client.get("/rooms", headers=first["headers"]).json()
    }
    second_rooms = {
        row["id"] for row in client.get("/rooms", headers=second["headers"]).json()
    }
    assert first_room_id in first_rooms
    assert second_room_id not in first_rooms
    assert second_room_id in second_rooms
    assert first_room_id not in second_rooms

    assert create_session(client, first, first_room_id).status_code == 201
    assert create_session(client, second, second_room_id).status_code == 201
    assert create_session(client, first, second_room_id).status_code == 403

def test_csv_export_neutralises_spreadsheet_formulas(client: TestClient):
    organiser = register_user(client, "csv_teacher", role="organiser")
    student = register_user(client, "csv_student")
    room_id = create_room(client, organiser, "601")
    enroll(client, student, room_id)
    session = create_session(
        client,
        organiser,
        room_id,
        subject="=1+1",
    ).json()

    db = TestSessionLocal()
    try:
        student_row = db.get(User, student["user"]["id"])
        student_row.display_name = "=HYPERLINK(\"https://example.invalid\",\"click\")"
        db.commit()
    finally:
        db.close()

    response = client.get(
        "/attendance/export.csv",
        params={"session_id": session["id"]},
        headers=organiser["headers"],
    )
    assert response.status_code == 200
    assert "'=HYPERLINK" in response.text
    assert "'=1+1" in response.text

def test_future_session_is_visible_to_owner_but_not_student(client: TestClient):
    organiser = register_user(client, "scheduled_teacher", role="organiser")
    student = register_user(client, "scheduled_student")
    room_id = create_room(client, organiser, "701")
    enroll(client, student, room_id)
    future_session = create_session(
        client,
        organiser,
        room_id,
        start_offset_minutes=5,
        subject="Scheduled Class",
    )
    assert future_session.status_code == 201, future_session.text
    session_id = future_session.json()["id"]

    owner_sessions = client.get("/sessions/active", headers=organiser["headers"])
    assert owner_sessions.status_code == 200
    assert session_id in {item["id"] for item in owner_sessions.json()}
    owner_item = next(item for item in owner_sessions.json() if item["id"] == session_id)
    assert owner_item["attendance_open"] is False

    student_sessions = client.get("/sessions/active", headers=student["headers"])
    assert student_sessions.status_code == 200
    assert session_id not in {item["id"] for item in student_sessions.json()}

def test_production_login_rate_limit_returns_429(client: TestClient, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("RENDER", raising=False)

    for _ in range(10):
        response = client.post(
            "/auth/login",
            json={"username": "rate_limit_user", "password": "wrong-password"},
        )
        assert response.status_code == 401

    limited = client.post(
        "/auth/login",
        json={"username": "rate_limit_user", "password": "wrong-password"},
    )
    assert limited.status_code == 429
    assert int(limited.headers["Retry-After"]) > 0
