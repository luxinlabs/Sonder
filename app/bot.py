"""The Sonder voice agent: Pipecat pipeline wired to Claude tool-calling."""

import os
from pathlib import Path

from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import LLMContextAggregatorPair
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.anthropic.llm import AnthropicLLMService
from pipecat.transports.websocket.fastapi import FastAPIWebsocketParams, FastAPIWebsocketTransport

from app import calendar_tools, memory_store

PIPER_MODELS_DIR = Path(__file__).parent.parent / "models" / "piper"

SYSTEM_PROMPT = """You are Sonder, the front-desk voice assistant for a medical clinic.

Scope: booking, rescheduling, and cancelling appointments, and basic clinic FAQ
(hours are 9am-5pm Monday-Friday; we accept most major PPO insurance plans).
Never give medical advice, diagnoses, or medication guidance. If asked anything
clinical, say a nurse will call them back.

As soon as the call connects, call get_patient_context with the caller's phone
number (given to you in the first user turn) before saying anything else. If
they're a known patient, greet them by name and reference their last visit
naturally. If they're not found, greet them as a new caller.

This is a live phone call, not a chat window: keep every response short,
spoken, and conversational. Never use bullet points, markdown, or numbered
lists in your responses.
"""


async def get_patient_context(params, phone_number: str):
    """Look up a patient's record and upcoming appointment by phone number.

    Args:
        phone_number: The caller's phone number in E.164 format.
    """
    patient = memory_store.get_patient_by_phone(phone_number)
    if not patient:
        await params.result_callback({"found": False})
        return
    upcoming = calendar_tools.get_upcoming_appointment(patient["id"])
    await params.result_callback(
        {
            "found": True,
            "patient_id": patient["id"],
            "name": patient["name"],
            "last_visit_reason": patient["last_visit_reason"],
            "medications": patient["medications"],
            "notes": patient["notes"],
            "upcoming_appointment": upcoming,
        }
    )


async def list_open_slots(params, days_ahead: int = 5):
    """List open appointment slots over the next several business days.

    Args:
        days_ahead: How many days ahead to search for open slots.
    """
    slots = calendar_tools.get_open_slots(days_ahead=days_ahead, limit=6)
    await params.result_callback({"slots": slots})


async def book_slot(
    params, patient_id: str, patient_name: str, start_iso: str, end_iso: str, reason: str = ""
):
    """Book an appointment for a patient at a specific open slot.

    Args:
        patient_id: The patient's unique ID, from get_patient_context.
        patient_name: The patient's full name.
        start_iso: ISO 8601 start datetime of the chosen slot.
        end_iso: ISO 8601 end datetime of the chosen slot.
        reason: Brief reason for the visit.
    """
    event = calendar_tools.book_appointment(start_iso, end_iso, patient_name, patient_id, reason)
    memory_store.set_upcoming_appt(patient_id, event["event_id"])
    await params.result_callback({"booked": True, "start": start_iso})


async def cancel_slot(params, patient_id: str, event_id: str):
    """Cancel a patient's previously booked appointment.

    Args:
        patient_id: The patient's unique ID.
        event_id: The calendar event ID to cancel, from get_patient_context.
    """
    calendar_tools.cancel_appointment(event_id)
    memory_store.set_upcoming_appt(patient_id, None)
    await params.result_callback({"cancelled": True})


def _build_stt_and_tts():
    """Pick cloud (Deepgram+Cartesia) or local (Whisper MLX+Piper) voice services.

    Cloud wins when both its keys are set in .env; otherwise falls back to the
    fully local, no-signup path. Imports are lazy so an unavailable path (e.g.
    local packages still installing) doesn't break the other one.
    """
    if os.environ.get("DEEPGRAM_API_KEY") and os.environ.get("CARTESIA_API_KEY"):
        from pipecat.services.cartesia.tts import CartesiaTTSService
        from pipecat.services.deepgram.stt import DeepgramSTTService

        logger.info("Voice services: Deepgram STT + Cartesia TTS (cloud)")
        stt = DeepgramSTTService(api_key=os.environ["DEEPGRAM_API_KEY"])
        tts = CartesiaTTSService(
            api_key=os.environ["CARTESIA_API_KEY"],
            voice_id=os.environ.get("CARTESIA_VOICE_ID", "79a125e8-cd45-4c13-8a67-188112f4dd22"),
        )
        return stt, tts

    from pipecat.services.piper.tts import PiperTTSService
    from pipecat.services.whisper.stt import MLXModel, WhisperSTTServiceMLX

    logger.info("Voice services: Whisper MLX STT + Piper TTS (local, no accounts)")
    stt = WhisperSTTServiceMLX(model=MLXModel.SMALL)
    tts = PiperTTSService(
        voice_id=os.environ.get("PIPER_VOICE", "en_US-lessac-medium"),
        download_dir=PIPER_MODELS_DIR,
    )
    return stt, tts


def _extract_transcript(context: LLMContext) -> list[dict]:
    turns = []
    for msg in context.get_messages(truncate_large_values=True):
        if isinstance(msg, dict):
            turns.append({"role": msg.get("role"), "content": msg.get("content")})
    return turns


def build_call_worker(
    websocket,
    stream_sid: str,
    call_sid: str,
    caller_phone: str,
    call_id: str,
) -> PipelineWorker:
    serializer = TwilioFrameSerializer(
        stream_sid=stream_sid,
        call_sid=call_sid,
        account_sid=os.environ["TWILIO_ACCOUNT_SID"],
        auth_token=os.environ["TWILIO_AUTH_TOKEN"],
    )

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            serializer=serializer,
            audio_in_sample_rate=8000,
            audio_out_sample_rate=8000,
            add_wav_header=False,
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    stt, tts = _build_stt_and_tts()
    llm = AnthropicLLMService(
        api_key=os.environ["ANTHROPIC_API_KEY"],
        settings=AnthropicLLMService.Settings(
            model="claude-sonnet-5", system_instruction=SYSTEM_PROMPT
        ),
    )

    context = LLMContext(
        messages=[
            {
                "role": "user",
                "content": (
                    f"[Call connected. Caller phone number: {caller_phone}. "
                    "Look them up now with get_patient_context, then greet them.]"
                ),
            }
        ],
        tools=[get_patient_context, list_open_slots, book_slot, cancel_slot],
    )
    context_aggregator = LLMContextAggregatorPair(context)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            context_aggregator.user(),
            llm,
            tts,
            transport.output(),
            context_aggregator.assistant(),
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(audio_in_sample_rate=8000, audio_out_sample_rate=8000),
    )

    @worker.event_handler("on_pipeline_finished")
    async def on_finished(worker, frame):
        memory_store.save_transcript(call_id, _extract_transcript(context))
        memory_store.end_call(call_id)
        logger.info(f"Call {call_id} finished, transcript saved")

    return worker
