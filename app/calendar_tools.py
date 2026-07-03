"""Google Calendar scheduling tools exposed to the voice agent.

Appointments are tagged with extendedProperties.private.patient_id so we can
look up "does this patient have an upcoming appointment" straight from the
calendar, without a separate scheduling database.
"""

import datetime as dt
import os

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CLIENT_SECRET_FILE = os.environ.get(
    "GOOGLE_CLIENT_SECRET_FILE", "credentials/client_secret.json"
)
TOKEN_FILE = os.path.join(os.path.dirname(CLIENT_SECRET_FILE), "token.json")
CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID", "primary")

BUSINESS_START_HOUR = 9
BUSINESS_END_HOUR = 17
SLOT_MINUTES = 30
LOCAL_TZ = dt.datetime.now().astimezone().tzinfo


def _service():
    if not os.path.exists(TOKEN_FILE):
        raise RuntimeError(
            f"No {TOKEN_FILE} found. Run `python3 app/google_auth_setup.py` "
            "once to authorize Google Calendar access."
        )
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)


def get_open_slots(days_ahead: int = 5, limit: int = 8) -> list[dict]:
    """Return up to `limit` open business-hour slots over the next `days_ahead` days."""
    svc = _service()
    now = dt.datetime.now(LOCAL_TZ)
    window_start = now
    window_end = now + dt.timedelta(days=days_ahead)

    busy = (
        svc.freebusy()
        .query(
            body={
                "timeMin": window_start.isoformat(),
                "timeMax": window_end.isoformat(),
                "items": [{"id": CALENDAR_ID}],
            }
        )
        .execute()["calendars"][CALENDAR_ID]["busy"]
    )
    busy_ranges = [
        (dt.datetime.fromisoformat(b["start"]), dt.datetime.fromisoformat(b["end"]))
        for b in busy
    ]

    slots = []
    day = window_start.date()
    while len(slots) < limit and day <= window_end.date():
        if day.weekday() < 5:  # skip weekends
            cursor = dt.datetime.combine(day, dt.time(BUSINESS_START_HOUR), LOCAL_TZ)
            day_end = dt.datetime.combine(day, dt.time(BUSINESS_END_HOUR), LOCAL_TZ)
            while cursor + dt.timedelta(minutes=SLOT_MINUTES) <= day_end:
                slot_end = cursor + dt.timedelta(minutes=SLOT_MINUTES)
                if cursor > now and not any(
                    cursor < b_end and slot_end > b_start
                    for b_start, b_end in busy_ranges
                ):
                    slots.append(
                        {
                            "start": cursor.isoformat(),
                            "end": slot_end.isoformat(),
                            "label": cursor.strftime("%A %b %d at %-I:%M %p"),
                        }
                    )
                    if len(slots) >= limit:
                        break
                cursor += dt.timedelta(minutes=SLOT_MINUTES)
        day += dt.timedelta(days=1)
    return slots


def book_appointment(
    start_iso: str,
    end_iso: str,
    patient_name: str,
    patient_id: str,
    reason: str = "",
) -> dict:
    svc = _service()
    event = (
        svc.events()
        .insert(
            calendarId=CALENDAR_ID,
            body={
                "summary": f"{patient_name} — {reason or 'appointment'}",
                "description": f"Booked by Sonder voice agent.\nReason: {reason}",
                "start": {"dateTime": start_iso},
                "end": {"dateTime": end_iso},
                "extendedProperties": {"private": {"patient_id": patient_id}},
            },
        )
        .execute()
    )
    return {"event_id": event["id"], "html_link": event.get("htmlLink"), "start": start_iso}


def get_upcoming_appointment(patient_id: str) -> dict | None:
    svc = _service()
    now = dt.datetime.now(LOCAL_TZ).isoformat()
    events = (
        svc.events()
        .list(
            calendarId=CALENDAR_ID,
            timeMin=now,
            privateExtendedProperty=f"patient_id={patient_id}",
            singleEvents=True,
            orderBy="startTime",
            maxResults=1,
        )
        .execute()
        .get("items", [])
    )
    if not events:
        return None
    e = events[0]
    return {"event_id": e["id"], "start": e["start"].get("dateTime"), "summary": e.get("summary")}


def reschedule_appointment(event_id: str, new_start_iso: str, new_end_iso: str) -> dict:
    svc = _service()
    event = (
        svc.events()
        .patch(
            calendarId=CALENDAR_ID,
            eventId=event_id,
            body={"start": {"dateTime": new_start_iso}, "end": {"dateTime": new_end_iso}},
        )
        .execute()
    )
    return {"event_id": event["id"], "start": new_start_iso}


def cancel_appointment(event_id: str) -> None:
    svc = _service()
    svc.events().delete(calendarId=CALENDAR_ID, eventId=event_id).execute()
