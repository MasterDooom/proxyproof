from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

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


def create_room(client: TestClient) -> int:
    response = client.post(
        "/rooms",
        json={"building": "AB1", "room_code": "301", "display_name": "AB1-301"},
    )
    assert response.status_code == 201
    return response.json()["id"]


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def test_health(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_create_and_list_room(client: TestClient):
    room_id = create_room(client)
    response = client.get("/rooms")
    assert response.status_code == 200
    assert response.json()[0]["id"] == room_id


def test_duplicate_room_code_is_rejected(client: TestClient):
    create_room(client)
    response = client.post(
        "/rooms",
        json={"building": "AB1", "room_code": "301", "display_name": "Duplicate room"},
    )
    assert response.status_code == 409


def test_attendance_window_is_fifteen_minutes(client: TestClient):
    room_id = create_room(client)
    scheduled_start = datetime.now(timezone.utc) - timedelta(minutes=2)
    response = client.post(
        "/sessions",
        json={
            "room_id": room_id,
            "subject_label": "Engineering Mathematics",
            "scheduled_start_at": iso_utc(scheduled_start),
        },
    )
    assert response.status_code == 201
    data = response.json()
    start = datetime.fromisoformat(data["scheduled_start_at"])
    deadline = datetime.fromisoformat(data["attendance_deadline"])
    assert (deadline - start) == timedelta(minutes=15)
    assert data["attendance_open"] is True
    assert len(client.get("/sessions/active").json()) == 1


def test_session_outside_attendance_window_is_rejected(client: TestClient):
    room_id = create_room(client)
    scheduled_start = datetime.now(timezone.utc) - timedelta(minutes=20)
    response = client.post(
        "/sessions",
        json={
            "room_id": room_id,
            "subject_label": "Physics",
            "scheduled_start_at": iso_utc(scheduled_start),
        },
    )
    assert response.status_code == 422
    assert "window" in response.json()["detail"].lower()


def test_closed_session_is_removed_from_active_list(client: TestClient):
    room_id = create_room(client)
    scheduled_start = datetime.now(timezone.utc) - timedelta(minutes=1)
    created = client.post(
        "/sessions",
        json={
            "room_id": room_id,
            "subject_label": "Physics",
            "scheduled_start_at": iso_utc(scheduled_start),
        },
    )
    assert created.status_code == 201
    session_id = created.json()["id"]

    closed = client.post(f"/sessions/{session_id}/close")
    assert closed.status_code == 200
    assert closed.json()["status"] == "closed"
    assert client.get("/sessions/active").json() == []
