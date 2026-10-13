from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text


BACKEND_DIR = Path(__file__).resolve().parents[1]


def _run_migrations(database_path: Path) -> None:
    env = os.environ.copy()
    env.pop("RENDER", None)
    env["APP_ENV"] = "development"
    env["DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + "\n" + result.stderr


def test_migrations_build_a_fresh_database(tmp_path: Path):
    database_path = tmp_path / "fresh.sqlite"
    _run_migrations(database_path)

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        assert {
            "alembic_version",
            "users",
            "api_tokens",
            "devices",
            "rooms",
            "room_enrollments",
            "attendance_sessions",
            "session_ble_tags",
            "attendance_records",
        }.issubset(set(inspector.get_table_names()))
        session_columns = {item["name"] for item in inspector.get_columns("attendance_sessions")}
        assert "created_by_user_id" in session_columns
        assert engine.connect().execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one() == "20261013_0003"
    finally:
        engine.dispose()


def test_migrations_adopt_legacy_schema_without_losing_rows(tmp_path: Path):
    database_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username VARCHAR(64) NOT NULL UNIQUE,
                display_name VARCHAR(120) NOT NULL,
                password_hash VARCHAR(256) NOT NULL,
                role VARCHAR(16) NOT NULL,
                is_active BOOLEAN NOT NULL,
                created_at DATETIME NOT NULL
            );
            CREATE TABLE rooms (
                id INTEGER PRIMARY KEY,
                building VARCHAR(80) NOT NULL,
                room_code VARCHAR(40) NOT NULL,
                display_name VARCHAR(120) NOT NULL,
                is_active BOOLEAN NOT NULL,
                created_at DATETIME NOT NULL,
                CONSTRAINT uq_room_building_code UNIQUE (building, room_code)
            );
            CREATE TABLE attendance_sessions (
                id VARCHAR(36) PRIMARY KEY,
                room_id INTEGER NOT NULL REFERENCES rooms(id),
                subject_label VARCHAR(120) NOT NULL,
                scheduled_start_at DATETIME NOT NULL,
                attendance_deadline DATETIME NOT NULL,
                status VARCHAR(16) NOT NULL,
                created_at DATETIME NOT NULL
            );
            CREATE TABLE session_ble_tags (
                session_id VARCHAR(36) PRIMARY KEY REFERENCES attendance_sessions(id),
                tag VARCHAR(12) NOT NULL UNIQUE,
                created_at DATETIME NOT NULL
            );
            INSERT INTO users VALUES (
                17, 'legacy_student', 'Legacy Student', 'old-hash', 'student', 1,
                '2026-10-13 02:00:00'
            );
            INSERT INTO rooms VALUES (
                9, 'AB1', '301', 'AB1-301', 1, '2026-10-13 02:00:00'
            );
            INSERT INTO attendance_sessions VALUES (
                'legacy-session-001', 9, 'Engineering Mathematics',
                '2026-10-13 02:00:00', '2026-10-13 02:15:00', 'closed',
                '2026-10-13 02:00:00'
            );
            INSERT INTO session_ble_tags VALUES (
                'legacy-session-001', '010203a0b0c0', '2026-10-13 02:00:00'
            );
            """
        )
        connection.commit()

    _run_migrations(database_path)

    engine = create_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT username FROM users WHERE id = 17")
            ).scalar_one() == "legacy_student"
            row = connection.execute(
                text(
                    "SELECT room_id, subject_label, status, created_by_user_id "
                    "FROM attendance_sessions WHERE id = 'legacy-session-001'"
                )
            ).one()
            assert row.room_id == 9
            assert row.subject_label == "Engineering Mathematics"
            assert row.status == "closed"
            assert row.created_by_user_id is None
            assert connection.execute(
                text("SELECT tag FROM session_ble_tags WHERE session_id = 'legacy-session-001'")
            ).scalar_one() == "010203a0b0c0"
        assert {"devices", "room_enrollments", "attendance_records"}.issubset(
            set(inspect(engine).get_table_names())
        )
    finally:
        engine.dispose()
