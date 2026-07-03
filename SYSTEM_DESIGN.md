# Sonder — Clinical Voice Agent

*A phone number a clinic can staff with an AI that remembers every patient, books their next visit, and closes the loop before they no-show.*

## Hackathon fit

Judging: completeness, innovation, real-life problem solving, sponsored product usage → AI screens to top 5, human judges pick top 3 from live demos.

- **Completeness**: mature stack (Twilio/Pipecat voice, Claude tool-calling) means the build hours go to integration, not invention — highest odds of a fully working system by demo time.
- **Sponsored product usage**: deployed on Tencent EdgeOne's Makers platform via the `claude-agent-starter-python` template — memory, tool management, and the agent runtime are EdgeOne's, not bolted on afterward. This is the strongest sponsor-fit angle available.
- **Real-life problem**: clinic phone-tag, no-shows, and front-desk overload.
- **Demo theater**: live voice call → visible calendar update. Reads well both to an AI reviewing the repo/README and to a human watching the live demo.

Because judging is two-stage, the repo itself needs to read as complete (clear README, working deploy, visible EdgeOne usage in code) for the AI pass — not just perform well live for the human pass.

## Deployment target

- Platform: [Tencent EdgeOne Makers](https://console.tencentcloud.com/edgeone/makers/new?template=claude-agent-starter-python&from=within&fromAgent=1&agentLang=python)
- Template: `claude-agent-starter-python` (Python stack)
- Implication: the agent service is a Python app running on EdgeOne's edge/serverless runtime — Pipecat (Python) is a natural fit here, and EdgeOne's own memory/tool-management primitives should be used directly rather than reimplemented.

## Architecture

```
                    ┌─────────────────────────────────────────┐
   Patient calls    │        EDGEONE AGENT RUNTIME (Python)    │
  ───────────────►  │  ┌─────────────┐   ┌──────────────────┐ │
   Twilio number     │  │ Pipecat     │   │ Claude (agent)   │ │
   (PSTN)            │  │ pipeline:   │◄─►│ + tool-calling   │ │
                     │  │ STT→LLM→TTS │   │ + system prompt  │ │
                     │  └─────────────┘   └────────┬─────────┘ │
                     │                              │           │
                     │              ┌───────────────┼────────┐  │
                     │              ▼               ▼        ▼  │
                     │       Patient Memory   Calendar   SMS/   │
                     │       (EdgeOne KV)      Tool       Notify│
                     └──────────────┼──────────────┼───────┼───┘
                                    │              │       │
                                    ▼              ▼       ▼
                             {patient_id:    Google Calendar  Twilio SMS
                              history,       or slot-grid DB
                              last_visit,
                              meds, notes}
                                    │
                                    ▼
                          ┌──────────────────┐
                          │  Live Dashboard   │  ← websocket, for demo theater
                          │  (transcript +    │
                          │   calendar view)  │
                          └──────────────────┘
```

## Components

**Telephony** — Twilio number + Media Streams, feeding a Pipecat pipeline (reuse Call Me Tomorrow scaffolding).

**Agent runtime** — hosted on EdgeOne Makers (`claude-agent-starter-python`). Deploy the agent *on* EdgeOne so tool-management and memory are visibly the sponsor's infrastructure, not a wrapper around it.

**Tool contract** (functions exposed to Claude):
- `get_patient_record(phone_number)` → history, last visit reason, upcoming appt
- `get_open_slots(date_range)`
- `book_appointment(patient_id, slot)` / `reschedule_appointment` / `cancel_appointment`
- `send_sms_confirmation(patient_id, message)`
- `log_call_summary(patient_id, summary)` → writes back into memory for the *next* call

**Memory store** — EdgeOne KV, keyed by phone number:
```
patient_id → { name, dob, last_visit_reason, meds, upcoming_appt, call_history[] }
```

**Calendar backend** — pick one, don't build both:
- Google Calendar API if OAuth goes smoothly (real calendar on screen = better demo)
- fallback: a simple slot-grid table + dashboard, no OAuth risk

**Dashboard** — thin page, websocket-fed, showing live transcript + calendar update. Pure demo theater, keep to ~1 page.

## Call flow

1. Patient calls → Twilio streams media into the Pipecat pipeline running on EdgeOne.
2. Agent looks up caller by phone number → gets memory → opens with context ("Hi Maria, last time you mentioned knee pain — how's that doing?").
3. Intent resolves to book/reschedule/cancel/FAQ.
4. Agent checks slots, books, triggers SMS confirmation.
5. On hangup, agent writes a structured summary back to memory for the next call or front-desk review.
6. Dashboard reflects the booking live.

## MVP scope cuts

- 3–5 seeded fake patients mapped to phone numbers you control — don't build patient onboarding.
- No real EHR, no HIPAA work — note "production would need X" in the pitch, don't build it.
- Single active call at a time — no concurrency handling.
- Narrow the agent's competence to scheduling/hours/insurance FAQ only. Never let it attempt clinical advice — scope and liability trap, and judges will probe it.

## Build order (10-hour budget)

| Hours | Task |
|---|---|
| 0–2 | Twilio + Pipecat skeleton up, verify STT→LLM→TTS round trip |
| 2–4 | Wire Claude tool-calling against a mocked calendar/patient backend |
| 4–6 | Move memory + tools onto EdgeOne runtime (`claude-agent-starter-python`); verify persistence across two separate calls — this is the sponsor-fit proof |
| 6–8 | Dashboard: live transcript + calendar view |
| 8–9 | Outbound reminder call flow (clinic calls patient back) |
| 9–10 | Rehearse both demo scenarios end-to-end; polish README for AI screening pass |

## Key risks

- **Latency**: keep EdgeOne deployment region close to Twilio's media region; use fast STT/TTS (Deepgram, Cartesia/ElevenLabs turbo).
- **Live OAuth failure on stage**: have the slot-grid fallback ready even if planning to use Google Calendar.
- **ASR mishearing medical terms**: don't test that surface — keep the demo script inside booking/rescheduling.

## Demo script

Judge calls the number live → agent recognizes them as a seeded "returning patient" and opens with remembered context → books an appointment → dashboard's calendar updates in real time → call ends → trigger a scripted outbound reminder call to a phone on stage to show the loop closing both directions.
