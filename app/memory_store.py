"""Patient memory + call log persistence (SQLite) shared by the voice agent and the dashboard."""

import datetime as dt
import json
import os
import sqlite3
import uuid

DB_PATH = os.environ.get("SONDER_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "sonder.db"))


def normalize_phone(raw: str) -> str:
    digits = "".join(c for c in raw if c.isdigit())
    if raw.startswith("+"):
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return "+" + digits


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = _connect()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS patients (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT UNIQUE NOT NULL,
            dob TEXT,
            last_visit_reason TEXT,
            medications TEXT,
            notes TEXT,
            upcoming_appt_event_id TEXT
        );
        CREATE TABLE IF NOT EXISTS calls (
            id TEXT PRIMARY KEY,
            patient_id TEXT REFERENCES patients(id),
            phone TEXT,
            direction TEXT,
            started_at TEXT,
            ended_at TEXT,
            transcript TEXT DEFAULT '[]',
            summary TEXT
        );
        """
    )
    conn.commit()
    conn.close()


def get_patient_by_phone(phone: str) -> dict | None:
    conn = _connect()
    row = conn.execute(
        "SELECT * FROM patients WHERE phone = ?", (normalize_phone(phone),)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def get_patient(patient_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM patients WHERE id = ?", (patient_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def list_patients() -> list[dict]:
    conn = _connect()
    rows = conn.execute("SELECT * FROM patients ORDER BY name").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def upsert_patient(
    phone: str,
    name: str,
    dob: str = "",
    last_visit_reason: str = "",
    medications: str = "",
    notes: str = "",
    patient_id: str | None = None,
) -> dict:
    phone = normalize_phone(phone)
    conn = _connect()
    existing = conn.execute("SELECT id FROM patients WHERE phone = ?", (phone,)).fetchone()
    pid = patient_id or (existing["id"] if existing else str(uuid.uuid4()))
    conn.execute(
        """
        INSERT INTO patients (id, name, phone, dob, last_visit_reason, medications, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name=excluded.name, phone=excluded.phone, dob=excluded.dob,
            last_visit_reason=excluded.last_visit_reason,
            medications=excluded.medications, notes=excluded.notes
        """,
        (pid, name, phone, dob, last_visit_reason, medications, notes),
    )
    conn.commit()
    conn.close()
    return get_patient(pid)


def set_upcoming_appt(patient_id: str, event_id: str | None) -> None:
    conn = _connect()
    conn.execute(
        "UPDATE patients SET upcoming_appt_event_id = ? WHERE id = ?", (event_id, patient_id)
    )
    conn.commit()
    conn.close()


def delete_patient(patient_id: str) -> None:
    conn = _connect()
    conn.execute("DELETE FROM patients WHERE id = ?", (patient_id,))
    conn.commit()
    conn.close()


def create_call(phone: str, direction: str, patient_id: str | None = None) -> str:
    call_id = str(uuid.uuid4())
    conn = _connect()
    conn.execute(
        "INSERT INTO calls (id, patient_id, phone, direction, started_at, transcript) VALUES (?, ?, ?, ?, ?, ?)",
        (call_id, patient_id, normalize_phone(phone), direction, dt.datetime.now().isoformat(), "[]"),
    )
    conn.commit()
    conn.close()
    return call_id


def append_transcript(call_id: str, role: str, text: str) -> None:
    conn = _connect()
    row = conn.execute("SELECT transcript FROM calls WHERE id = ?", (call_id,)).fetchone()
    turns = json.loads(row["transcript"]) if row else []
    turns.append({"role": role, "text": text, "at": dt.datetime.now().isoformat()})
    conn.execute("UPDATE calls SET transcript = ? WHERE id = ?", (json.dumps(turns), call_id))
    conn.commit()
    conn.close()


def save_transcript(call_id: str, transcript: list[dict]) -> None:
    conn = _connect()
    conn.execute("UPDATE calls SET transcript = ? WHERE id = ?", (json.dumps(transcript), call_id))
    conn.commit()
    conn.close()


def end_call(call_id: str, summary: str = "") -> None:
    conn = _connect()
    conn.execute(
        "UPDATE calls SET ended_at = ?, summary = ? WHERE id = ?",
        (dt.datetime.now().isoformat(), summary, call_id),
    )
    conn.commit()
    conn.close()


def get_call(call_id: str) -> dict | None:
    conn = _connect()
    row = conn.execute("SELECT * FROM calls WHERE id = ?", (call_id,)).fetchone()
    conn.close()
    if not row:
        return None
    d = dict(row)
    d["transcript"] = json.loads(d["transcript"])
    return d


def list_calls(limit: int = 50) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        """
        SELECT calls.*, patients.name AS patient_name
        FROM calls LEFT JOIN patients ON calls.patient_id = patients.id
        ORDER BY started_at DESC LIMIT ?
        """,
        (limit,),
    ).fetchall()
    conn.close()
    out = []
    for r in rows:
        d = dict(r)
        d["transcript"] = json.loads(d["transcript"])
        out.append(d)
    return out
