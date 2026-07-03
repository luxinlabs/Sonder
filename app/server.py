"""FastAPI server: Twilio TwiML + media-stream websocket, outbound test-call trigger,
and a small REST API backing the dashboard."""

import json
import os
import uuid

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel
from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import Connect, VoiceResponse

from app import memory_store
from app.bot import build_call_worker
from pipecat.workers.runner import WorkerRunner

load_dotenv()
memory_store.init_db()

app = FastAPI(title="Sonder")

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _twilio_client() -> TwilioClient:
    return TwilioClient(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])


def _public_base_url() -> str:
    url = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    if not url:
        raise HTTPException(500, "PUBLIC_BASE_URL is not set (ngrok URL)")
    return url


# ---- Outbound test call ----------------------------------------------------


class OutboundCallRequest(BaseModel):
    to: str | None = None


@app.post("/api/calls/outbound")
def place_outbound_call(body: OutboundCallRequest):
    to_number = memory_store.normalize_phone(body.to or os.environ["TEST_CALL_TO_NUMBER"])
    patient = memory_store.get_patient_by_phone(to_number)
    call_id = memory_store.create_call(
        phone=to_number, direction="outbound", patient_id=patient["id"] if patient else None
    )

    twilio = _twilio_client()
    call = twilio.calls.create(
        to=to_number,
        from_=os.environ["TWILIO_PHONE_NUMBER"],
        url=f"{_public_base_url()}/twiml/{call_id}",
    )
    return {"call_id": call_id, "twilio_call_sid": call.sid, "to": to_number}


# ---- Twilio webhooks --------------------------------------------------------


@app.api_route("/twiml/{call_id}", methods=["GET", "POST"])
def twiml(call_id: str):
    call = memory_store.get_call(call_id)
    if not call:
        raise HTTPException(404, "unknown call_id")

    ws_url = _public_base_url().replace("https://", "wss://").replace("http://", "ws://")
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=f"{ws_url}/ws/{call_id}")
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")


@app.post("/twiml/inbound")
async def twiml_inbound(request: Request):
    """Twilio voice webhook for the number's inbound calls: create a call record on the fly."""
    form = await request.form()
    from_number = memory_store.normalize_phone(form.get("From", ""))
    patient = memory_store.get_patient_by_phone(from_number)
    call_id = memory_store.create_call(
        phone=from_number, direction="inbound", patient_id=patient["id"] if patient else None
    )

    ws_url = _public_base_url().replace("https://", "wss://").replace("http://", "ws://")
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=f"{ws_url}/ws/{call_id}")
    response.append(connect)
    return HTMLResponse(content=str(response), media_type="application/xml")


@app.websocket("/ws/{call_id}")
async def media_stream(websocket: WebSocket, call_id: str):
    await websocket.accept()

    call = memory_store.get_call(call_id)
    if not call:
        await websocket.close()
        return

    # Twilio sends a "connected" event, then a "start" event before any media.
    stream_sid = None
    call_sid = None
    while True:
        message = await websocket.receive_text()
        data = json.loads(message)
        if data.get("event") == "start":
            stream_sid = data["start"]["streamSid"]
            call_sid = data["start"]["callSid"]
            break

    worker = build_call_worker(
        websocket=websocket,
        stream_sid=stream_sid,
        call_sid=call_sid,
        caller_phone=call["phone"],
        call_id=call_id,
    )

    runner = WorkerRunner(handle_sigint=False)
    await runner.add_workers(worker)
    await runner.run()


# ---- Dashboard REST API -----------------------------------------------------


class PatientIn(BaseModel):
    name: str
    phone: str
    dob: str = ""
    last_visit_reason: str = ""
    medications: str = ""
    notes: str = ""


@app.get("/api/patients")
def list_patients():
    return memory_store.list_patients()


@app.post("/api/patients")
def create_patient(body: PatientIn):
    return memory_store.upsert_patient(**body.model_dump())


@app.get("/api/patients/{patient_id}")
def get_patient(patient_id: str):
    patient = memory_store.get_patient(patient_id)
    if not patient:
        raise HTTPException(404, "not found")
    return patient


@app.patch("/api/patients/{patient_id}")
def update_patient(patient_id: str, body: PatientIn):
    return memory_store.upsert_patient(patient_id=patient_id, **body.model_dump())


@app.delete("/api/patients/{patient_id}")
def delete_patient(patient_id: str):
    memory_store.delete_patient(patient_id)
    return {"deleted": True}


@app.get("/api/calls")
def list_calls(limit: int = 50):
    return memory_store.list_calls(limit=limit)


@app.get("/api/calls/{call_id}")
def get_call(call_id: str):
    call = memory_store.get_call(call_id)
    if not call:
        raise HTTPException(404, "not found")
    return call


@app.get("/")
def dashboard():
    index = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index):
        return FileResponse(index)
    return HTMLResponse("<h1>Sonder</h1><p>Dashboard not built yet.</p>")
