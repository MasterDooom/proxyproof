"""ProxyProof API: authenticated room-specific attendance prototype.

This service is intended for local demos, not public deployment. BLE RSSI is
a rough proximity heuristic and cannot prove someone is inside a classroom.
"""
import csv
import hmac
import os
import time
from datetime import datetime, timedelta, timezone
from io import StringIO

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from sqlalchemy import or_, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .models import (
    ApiToken,
    AttendanceRecord,
    AttendanceSession,
    Device,
    Room,
    RoomEnrollment,
    SessionBleTag,
    User,
)
from .schemas import (
    AttendanceHistoryItem,
    AttendanceHistoryResponse,
    AttendanceMarkedResponse,
    AttendanceRosterItem,
    AttendanceRosterResponse,
    AuthResponse,
    BleAttendanceRequest,
    BleTokenOut,
    DeviceOut,
    DeviceRegisterRequest,
    LoginRequest,
    ManualAttendanceRequest,
    RegisterRequest,
    RoomCreate,
    RoomOut,
    SessionCreate,
    SessionOut,
    UserOut,
)
from .security import (
    BLE_TOKEN_ROTATION_SECONDS,
    MIN_RSSI_DBM,
    current_ble_slot,
    get_current_user,
    get_organiser_invite_code,
    hash_password,
    issue_access_token,
    make_ble_token,
    require_role,
    utc_now_naive,
    valid_ble_token,
    verify_password,
)

ATTENDANCE_GRACE_MINUTES = 15
ORGANISER_INVITE_CODE = get_organiser_invite_code()
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="ProxyProof API",
    description="Room-specific BLE attendance prototype",
    version="0.2.0",
)


def as_utc(value: datetime) -> datetime:
    """Interpret SQLite naive timestamps as UTC and return an aware UTC datetime."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def user_to_response(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
    )


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


def get_session_or_404(session_id: str, db: Session) -> AttendanceSession:
    item = db.get(AttendanceSession, session_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Session not found.")
    return item


def require_session_owner(item: AttendanceSession, user: User) -> None:
    """Restrict organiser management to sessions created by that organiser."""
    if user.role != "organiser" or item.created_by_user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="You are not authorised to manage this attendance session.",
        )


def require_room_enrollment(student_id: int, room_id: int, db: Session) -> RoomEnrollment:
    enrollment = db.scalar(
        select(RoomEnrollment).where(
            RoomEnrollment.user_id == student_id,
            RoomEnrollment.room_id == room_id,
        )
    )
    if enrollment is None:
        raise HTTPException(
            status_code=403,
            detail="You are not registered for this room. Register for the room first.",
        )
    return enrollment


def roster_item(
    student: User,
    record: AttendanceRecord | None,
) -> AttendanceRosterItem:
    return AttendanceRosterItem(
        student_id=student.id,
        username=student.username,
        display_name=student.display_name,
        status=record.status if record else None,
        marked_at=as_utc(record.marked_at) if record else None,
        method=record.method if record else None,
        rssi_at_mark=record.rssi_at_mark if record else None,
    )


@app.get("/")
def root() -> dict[str, str]:
    return {"name": "ProxyProof API", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict[str, str]:
    # Include a cheap datastore check so the host can detect DB outages too.
    db.execute(text("SELECT 1"))
    return {"status": "ok", "service": "proxyproof-api"}


@app.post("/auth/register", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> AuthResponse:
    username = payload.username.strip().lower()
    display_name = payload.display_name.strip()

    if payload.role == "organiser":
        supplied = payload.organiser_invite_code or ""
        if not hmac.compare_digest(supplied, ORGANISER_INVITE_CODE):
            raise HTTPException(status_code=403, detail="A valid organiser invite code is required.")

    if db.scalar(select(User).where(User.username == username)):
        raise HTTPException(status_code=409, detail="That username is already registered.")

    user = User(
        username=username,
        display_name=display_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="That username is already registered.") from exc

    db.refresh(user)
    raw_token, expires_at = issue_access_token(db, user)
    db.commit()
    return AuthResponse(
        access_token=raw_token,
        expires_at=expires_at,
        user=user_to_response(user),
    )


@app.post("/auth/login", response_model=AuthResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthResponse:
    user = db.scalar(select(User).where(User.username == payload.username.strip().lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect username or password.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="This account is inactive.")

    raw_token, expires_at = issue_access_token(db, user)
    db.commit()
    return AuthResponse(
        access_token=raw_token,
        expires_at=expires_at,
        user=user_to_response(user),
    )


@app.get("/auth/me", response_model=UserOut)
def auth_me(user: User = Depends(get_current_user)) -> UserOut:
    return user_to_response(user)


@app.post("/devices/register", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
def register_device(
    payload: DeviceRegisterRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("student")),
) -> DeviceOut:
    existing = db.scalar(select(Device).where(Device.user_id == user.id))
    if existing:
        if existing.device_key != payload.device_key:
            raise HTTPException(
                status_code=409,
                detail="This student already has a registered device. An organiser must approve a device change.",
            )
        if not existing.is_active:
            raise HTTPException(status_code=403, detail="This device has been deactivated.")
        return DeviceOut(
            id=existing.id,
            device_key=existing.device_key,
            is_active=existing.is_active,
            registered_at=as_utc(existing.registered_at),
        )

    reused = db.scalar(select(Device).where(Device.device_key == payload.device_key))
    if reused:
        raise HTTPException(status_code=409, detail="This device is already bound to another account.")

    device = Device(user_id=user.id, device_key=payload.device_key)
    db.add(device)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Device registration conflicts with an existing binding.") from exc
    db.refresh(device)
    return DeviceOut(
        id=device.id,
        device_key=device.device_key,
        is_active=device.is_active,
        registered_at=as_utc(device.registered_at),
    )


@app.get("/rooms", response_model=list[RoomOut])
def list_rooms(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> list[Room]:
    return list(
        db.scalars(
            select(Room)
            .where(Room.is_active.is_(True))
            .order_by(Room.building, Room.room_code)
        )
    )


@app.post("/rooms", response_model=RoomOut, status_code=status.HTTP_201_CREATED)
def create_room(
    payload: RoomCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role("organiser")),
) -> Room:
    room = Room(
        building=payload.building.strip(),
        room_code=payload.room_code.strip(),
        display_name=payload.display_name.strip(),
    )
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


@app.post("/rooms/{room_id}/enroll", response_model=RoomOut)
def enroll_in_room(
    room_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("student")),
) -> Room:
    room = db.get(Room, room_id)
    if room is None or not room.is_active:
        raise HTTPException(status_code=404, detail="Active room not found.")

    enrollment = db.scalar(
        select(RoomEnrollment).where(
            RoomEnrollment.user_id == user.id,
            RoomEnrollment.room_id == room.id,
        )
    )
    if enrollment is None:
        db.add(RoomEnrollment(user_id=user.id, room_id=room.id))
        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            # Another request may have enrolled the same user at the same time.
            if db.scalar(
                select(RoomEnrollment).where(
                    RoomEnrollment.user_id == user.id,
                    RoomEnrollment.room_id == room.id,
                )
            ) is None:
                raise HTTPException(status_code=409, detail="Room enrollment could not be saved.") from exc
    return room


@app.get("/rooms/my", response_model=list[RoomOut])
def my_rooms(
    db: Session = Depends(get_db),
    user: User = Depends(require_role("student")),
) -> list[Room]:
    return list(
        db.scalars(
            select(Room)
            .join(RoomEnrollment, RoomEnrollment.room_id == Room.id)
            .where(RoomEnrollment.user_id == user.id, Room.is_active.is_(True))
            .order_by(Room.building, Room.room_code)
        )
    )


@app.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("organiser")),
) -> SessionOut:
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

    item = AttendanceSession(
        room_id=room.id,
        created_by_user_id=user.id,
        subject_label=payload.subject_label,
        scheduled_start_at=scheduled_aware.replace(tzinfo=None),
        attendance_deadline=deadline_aware.replace(tzinfo=None),
        status="open",
    )
    db.add(item)
    try:
        db.flush()
        db.add(SessionBleTag(session_id=item.id, tag=os.urandom(6).hex()))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Could not create a unique room session.") from exc
    db.refresh(item)
    return session_to_response(item)


@app.get("/sessions/active", response_model=list[SessionOut])
def list_current_attendance_sessions(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SessionOut]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    query = (
        select(AttendanceSession)
        .where(
            AttendanceSession.status == "open",
            AttendanceSession.scheduled_start_at <= now,
            AttendanceSession.attendance_deadline >= now,
        )
        .order_by(AttendanceSession.scheduled_start_at)
    )
    if user.role == "student":
        query = query.join(
            RoomEnrollment, RoomEnrollment.room_id == AttendanceSession.room_id
        ).where(RoomEnrollment.user_id == user.id)
    elif user.role == "organiser":
        query = query.where(AttendanceSession.created_by_user_id == user.id)
    items = db.scalars(query).unique().all()
    return [session_to_response(item) for item in items]


@app.get("/sessions/{session_id}/current-token", response_model=BleTokenOut)
def get_current_ble_token(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("organiser")),
) -> BleTokenOut:
    item = get_session_or_404(session_id, db)
    require_session_owner(item, user)
    now = datetime.now(timezone.utc)
    if item.status != "open":
        raise HTTPException(status_code=409, detail="This session is closed.")
    if now < as_utc(item.scheduled_start_at) or now > as_utc(item.attendance_deadline):
        raise HTTPException(status_code=409, detail="BLE attendance is outside the 15-minute attendance window.")

    tag = db.get(SessionBleTag, item.id)
    if tag is None:
        raise HTTPException(status_code=500, detail="Session BLE tag is missing.")
    slot = current_ble_slot(time.time())
    expires_at = datetime.fromtimestamp(
        (slot + 1) * BLE_TOKEN_ROTATION_SECONDS, tz=timezone.utc
    )
    return BleTokenOut(
        session_id=item.id,
        session_tag=tag.tag,
        token=make_ble_token(item.id, slot),
        expires_at=expires_at,
        rotation_seconds=BLE_TOKEN_ROTATION_SECONDS,
    )


@app.get("/sessions/{session_id}/attendance", response_model=AttendanceRosterResponse)
def get_session_attendance(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("organiser")),
) -> AttendanceRosterResponse:
    item = get_session_or_404(session_id, db)
    require_session_owner(item, user)
    enrollments = db.scalars(
        select(RoomEnrollment)
        .where(RoomEnrollment.room_id == item.room_id)
        .order_by(RoomEnrollment.user_id)
    ).all()
    user_ids = [enrollment.user_id for enrollment in enrollments]
    users = {
        user.id: user
        for user in db.scalars(select(User).where(User.id.in_(user_ids))).all()
    } if user_ids else {}
    records = {
        record.student_id: record
        for record in db.scalars(
            select(AttendanceRecord).where(AttendanceRecord.session_id == item.id)
        ).all()
    }
    roster = [
        roster_item(users[student_id], records.get(student_id))
        for student_id in user_ids
        if student_id in users
    ]
    return AttendanceRosterResponse(
        session_id=item.id,
        room_name=item.room.display_name,
        subject_label=item.subject_label,
        scheduled_start_at=as_utc(item.scheduled_start_at),
        attendance_deadline=as_utc(item.attendance_deadline),
        attendance_open=session_to_response(item).attendance_open,
        enrolled_count=len(roster),
        present_count=sum(1 for row in roster if row.status == "present"),
        records=roster,
    )


@app.post("/sessions/{session_id}/attendance/manual", response_model=AttendanceRosterItem)
def manual_attendance(
    session_id: str,
    payload: ManualAttendanceRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("organiser")),
) -> AttendanceRosterItem:
    session = get_session_or_404(session_id, db)
    require_session_owner(session, user)
    student = db.get(User, payload.student_id)
    if student is None or student.role != "student":
        raise HTTPException(status_code=404, detail="Student not found.")
    require_room_enrollment(student.id, session.room_id, db)

    device = db.scalar(select(Device).where(Device.user_id == student.id, Device.is_active.is_(True)))
    record = db.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.session_id == session.id,
            AttendanceRecord.student_id == student.id,
        )
    )
    if record is None:
        record = AttendanceRecord(
            session_id=session.id,
            student_id=student.id,
            device_id=device.id if device else None,
            method="manual",
            rssi_at_mark=None,
            status=payload.status,
        )
        db.add(record)
    else:
        record.method = "manual"
        record.status = payload.status
        record.device_id = device.id if device else None
        record.rssi_at_mark = None
        record.marked_at = utc_now_naive()
    db.commit()
    db.refresh(record)
    return roster_item(student, record)


@app.post("/attendance/ble", response_model=AttendanceMarkedResponse)
def submit_ble_attendance(
    payload: BleAttendanceRequest,
    db: Session = Depends(get_db),
    student: User = Depends(require_role("student")),
) -> AttendanceMarkedResponse:
    device = db.scalar(
        select(Device).where(Device.user_id == student.id, Device.is_active.is_(True))
    )
    if device is None:
        raise HTTPException(status_code=409, detail="Register this phone before submitting attendance.")

    tag = db.scalar(select(SessionBleTag).where(SessionBleTag.tag == payload.session_tag.lower()))
    if tag is None:
        raise HTTPException(status_code=404, detail="Unknown room session advertisement.")
    session = get_session_or_404(tag.session_id, db)
    now = datetime.now(timezone.utc)
    if session.status != "open":
        raise HTTPException(status_code=409, detail="This attendance session is closed.")
    if now < as_utc(session.scheduled_start_at) or now > as_utc(session.attendance_deadline):
        raise HTTPException(status_code=422, detail="The 15-minute automatic attendance window has ended.")
    require_room_enrollment(student.id, session.room_id, db)

    if not valid_ble_token(session.id, payload.token, now_epoch=time.time()):
        raise HTTPException(status_code=401, detail="BLE token is invalid or expired.")
    if payload.rssi < MIN_RSSI_DBM:
        raise HTTPException(
            status_code=422,
            detail=f"Signal is too weak for the prototype proximity threshold ({MIN_RSSI_DBM} dBm).",
        )

    existing = db.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.session_id == session.id,
            AttendanceRecord.student_id == student.id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Attendance is already recorded for this session.")

    record = AttendanceRecord(
        session_id=session.id,
        student_id=student.id,
        device_id=device.id,
        marked_at=utc_now_naive(),
        method="ble",
        rssi_at_mark=payload.rssi,
        status="present",
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Attendance was already recorded.") from exc
    db.refresh(record)
    return AttendanceMarkedResponse(
        status="present",
        session_id=session.id,
        room_name=session.room.display_name,
        subject_label=session.subject_label,
        marked_at=as_utc(record.marked_at),
        method="ble",
    )


@app.get("/attendance/me", response_model=AttendanceHistoryResponse)
def my_attendance(
    db: Session = Depends(get_db),
    student: User = Depends(require_role("student")),
) -> AttendanceHistoryResponse:
    records = db.scalars(
        select(AttendanceRecord)
        .where(AttendanceRecord.student_id == student.id)
        .order_by(AttendanceRecord.marked_at.desc())
    ).all()
    items: list[AttendanceHistoryItem] = []
    record_by_session: dict[str, AttendanceRecord] = {}
    for record in records:
        session = db.get(AttendanceSession, record.session_id)
        if session is None:
            continue
        record_by_session[session.id] = record
        items.append(
            AttendanceHistoryItem(
                session_id=session.id,
                room_name=session.room.display_name,
                subject_label=session.subject_label,
                scheduled_start_at=as_utc(session.scheduled_start_at),
                marked_at=as_utc(record.marked_at),
                method=record.method,
                status=record.status,
                rssi_at_mark=record.rssi_at_mark,
            )
        )

    now = utc_now_naive()
    enrollments = db.scalars(
        select(RoomEnrollment).where(RoomEnrollment.user_id == student.id)
    ).all()
    eligible_ids: set[str] = set()
    for enrollment in enrollments:
        completed = db.scalars(
            select(AttendanceSession).where(
                AttendanceSession.room_id == enrollment.room_id,
                AttendanceSession.scheduled_start_at >= enrollment.created_at,
                AttendanceSession.scheduled_start_at <= now,
                or_(
                    AttendanceSession.status == "closed",
                    AttendanceSession.attendance_deadline < now,
                ),
            )
        ).all()
        eligible_ids.update(session.id for session in completed)

    present_count = sum(
        1
        for session_id in eligible_ids
        if (record := record_by_session.get(session_id)) is not None and record.status == "present"
    )
    percentage = round(100 * present_count / len(eligible_ids), 1) if eligible_ids else 0.0
    return AttendanceHistoryResponse(
        items=items,
        eligible_sessions=len(eligible_ids),
        present_sessions=present_count,
        percentage=percentage,
    )


@app.get("/attendance/export.csv")
def export_attendance_csv(
    session_id: str = Query(min_length=1),
    db: Session = Depends(get_db),
    user: User = Depends(require_role("organiser")),
) -> Response:
    session = get_session_or_404(session_id, db)
    require_session_owner(session, user)
    enrollments = db.scalars(
        select(RoomEnrollment).where(RoomEnrollment.room_id == session.room_id)
    ).all()
    user_ids = [enrollment.user_id for enrollment in enrollments]
    users = {
        user.id: user for user in db.scalars(select(User).where(User.id.in_(user_ids))).all()
    } if user_ids else {}
    records = {
        record.student_id: record
        for record in db.scalars(
            select(AttendanceRecord).where(AttendanceRecord.session_id == session.id)
        ).all()
    }
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["student_id", "username", "student_name", "room", "subject", "status", "method", "marked_at", "rssi_dbm"])
    for student_id in user_ids:
        user = users.get(student_id)
        if user is None:
            continue
        record = records.get(student_id)
        writer.writerow([
            user.id,
            user.username,
            user.display_name,
            session.room.display_name,
            session.subject_label,
            record.status if record else "absent",
            record.method if record else "",
            as_utc(record.marked_at).isoformat() if record else "",
            record.rssi_at_mark if record and record.rssi_at_mark is not None else "",
        ])
    filename = f"proxyproof-{session.room.room_code}-{session.id[:8]}.csv"
    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> SessionOut:
    item = get_session_or_404(session_id, db)
    if user.role == "student":
        require_room_enrollment(user.id, item.room_id, db)
    elif user.role == "organiser":
        require_session_owner(item, user)
    return session_to_response(item)


@app.post("/sessions/{session_id}/close", response_model=SessionOut)
def close_session(
    session_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("organiser")),
) -> SessionOut:
    item = get_session_or_404(session_id, db)
    require_session_owner(item, user)
    item.status = "closed"
    db.commit()
    db.refresh(item)
    return session_to_response(item)
