"""ProxyProof API: first runnable vertical slice.

Authentication and BLE token verification are intentionally the next stages.
Do not expose this prototype API to the public internet as-is.
"""
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import AttendanceSession, Room
from .schemas import RoomCreate, RoomOut, SessionCreate, SessionOut

ATTENDANCE_GRACE_MINUTES = 15
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="ProxyProof API",
    description="Room-specific BLE attendance prototype",
    version="0.1.0",
)


def as_utc(value: datetime) -> datetime:
    """Interpret SQLite naive timestamps as UTC and return an aware UTC datetime."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def session_to_response(item: AttendanceSession) -> SessionOut:
    now = datetime.now(timezone.utc)
    scheduled = as_utc(item.scheduled_start_at)
    deadline = as_utc(item.attendance_deadline)
    return SessionOut(
        id=item.id,
        room_id=item.room_id,
        room_name=item.room.display_name,
        subject_label=item.subject_label,
        scheduled_start_at=scheduled,
        attendance_deadline=deadline,
        status=item.status,
        attendance_open=item.status == "open" and scheduled <= now <= deadline,
    )


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "ProxyProof API", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "proxyproof-api"}


@app.post("/rooms", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
def create_room(payload: RoomCreate, db: Session = Depends(get_db)) -> Room:
    room = Room(
        building=payload.building.strip(),
        room_code=payload.room_code.strip(),
        display_name=payload.display_name.strip(),
    )
    if not room.building or not room.room_code or not room.display_name:
        raise HTTPException(status_code=422, detail="Room fields cannot be blank.")
    db.add(room)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A room with this building and room code already exists.",
        ) from exc
    db.refresh(room)
    return room


@app.get("/rooms", response_model=list[RoomOut])
def list_rooms(db: Session = Depends(get_db)) -> list[Room]:
    return list(db.scalars(select(Room).where(Room.is_active.is_(True)).order_by(Room.building, Room.room_code)))


@app.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(payload: SessionCreate, db: Session = Depends(get_db)) -> SessionOut:
    room = db.get(Room, payload.room_id)
    if room is None or not room.is_active:
        raise HTTPException(status_code=404, detail="Active room not found.")

    scheduled_aware = payload.scheduled_start_at.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    deadline_aware = scheduled_aware + timedelta(minutes=ATTENDANCE_GRACE_MINUTES)
    if now > deadline_aware:
        raise HTTPException(
            status_code=422,
            detail="The 15-minute automatic attendance window for this class has already expired.",
        )

    # SQLite does not preserve timezone offsets; store UTC-naive values and
    # consistently interpret them as UTC when reading them back.
    scheduled = scheduled_aware.replace(tzinfo=None)
    deadline = deadline_aware.replace(tzinfo=None)
    item = AttendanceSession(
        room_id=room.id,
        subject_label=payload.subject_label.strip(),
        scheduled_start_at=scheduled,
        attendance_deadline=deadline,
        status="open",
    )
    if not item.subject_label:
        raise HTTPException(status_code=422, detail="Subject label cannot be blank.")

    db.add(item)
    db.commit()
    db.refresh(item)
    return session_to_response(item)


@app.get("/sessions/active", response_model=list[SessionOut])
def list_current_attendance_sessions(db: Session = Depends(get_db)) -> list[SessionOut]:
    """Return sessions inside their attendance window; sessions in other rooms remain distinct."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    items = db.scalars(
        select(AttendanceSession)
        .where(
            AttendanceSession.status == "open",
            AttendanceSession.scheduled_start_at <= now,
            AttendanceSession.attendance_deadline >= now,
        )
        .order_by(AttendanceSession.scheduled_start_at)
    ).all()
    return [session_to_response(item) for item in items]


@app.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: str, db: Session = Depends(get_db)) -> SessionOut:
    item = db.get(AttendanceSession, session_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return session_to_response(item)


@app.post("/sessions/{session_id}/close", response_model=SessionOut)
def close_session(session_id: str, db: Session = Depends(get_db)) -> SessionOut:
    item = db.get(AttendanceSession, session_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    item.status = "closed"
    db.commit()
    db.refresh(item)
    return session_to_response(item)
