# Sonder — AI Voice Agent for Clinic Front Desks

> *A phone number a clinic staffs with AI. It remembers every patient, books their next visit, and closes the loop before they no-show.*

[![Built on EdgeOne](https://img.shields.io/badge/Runtime-Tencent%20EdgeOne%20Makers-00D4AA?style=flat-square)](https://console.tencentcloud.com/edgeone/makers)
[![Powered by Claude](https://img.shields.io/badge/AI-Claude%20(Anthropic)-5A4FCF?style=flat-square)](https://anthropic.com)
[![Twilio Voice](https://img.shields.io/badge/Telephony-Twilio-F22F46?style=flat-square)](https://twilio.com)
[![Deepgram STT](https://img.shields.io/badge/STT-Deepgram-13EF93?style=flat-square)](https://deepgram.com)

---

## What it does

Clinics lose ~27% of patients to unanswered calls and ~$150K/year to no-shows. Sonder solves both:

1. **Patient calls** the clinic's Twilio number — Sonder picks up instantly, 24/7.
2. **AI recognizes them** — Claude looks up the caller's history, last visit reason, and medications before saying hello.
3. **Books the appointment** — Sonder checks open slots and writes directly to Google Calendar in the same voice conversation.
4. **SMS confirmation fires** — Twilio sends the patient a confirmation before the call ends.
5. **Call summary saved** — the transcript and summary are written back to the patient's memory for the next call.
6. **Outbound reminders** — the clinic can trigger Sonder to call patients back, closing the loop in both directions.

All of this runs on **Tencent EdgeOne Makers** (`claude-agent-starter-python` template). Memory, tool management, and the agent runtime are EdgeOne's infrastructure — not bolted on afterward.

---

## Live demo flow

```
Judge dials the Sonder number
  → AI opens: "Hi Maria — last time you mentioned knee pain. How's that doing?"
  → Patient: "I'd like to see Dr. Lee on Thursday morning"
  → Sonder checks calendar, books the slot, dashboard updates live
  → SMS lands on judge's phone: "Confirmed: Dr. Lee, Thu 10am"
  → Clinic triggers outbound reminder → judge's phone rings again
```

---

## Architecture

```
                   ┌──────────────────────────────────────────┐
  Patient calls    │      EDGEONE AGENT RUNTIME (Python)       │
 ───────────────►  │  ┌─────────────┐   ┌──────────────────┐  │
  Twilio number    │  │   Pipecat   │   │  Claude (agent)  │  │
  (PSTN)           │  │  pipeline:  │◄─►│  + tool-calling  │  │
                   │  │ STT→LLM→TTS │   │  + system prompt │  │
                   │  └─────────────┘   └────────┬─────────┘  │
                   │                             │            │
                   │           ┌─────────────────┼──────────┐ │
                   │           ▼                 ▼          ▼ │
                   │    Patient Memory      Calendar    SMS /  │
                   │    (EdgeOne KV)         Tool       Notify │
                   └───────────┼─────────────────┼──────────┼─┘
                               │                 │          │
                               ▼                 ▼          ▼
                        SQLite patient     Google Calendar  Twilio SMS
                        profiles +
                        call history
                               │
                               ▼
                     ┌──────────────────┐
                     │  Live Dashboard  │  ← auto-refresh, for demo
                     │  (transcript +   │
                     │   calendar view) │
                     └──────────────────┘
```

### Sponsor stack

| Layer | Provider | Role |
|---|---|---|
| Agent runtime | **Tencent EdgeOne Makers** | Hosts the Python agent; KV memory + tool management |
| AI brain | **Claude (Anthropic)** | Intent parsing, tool-calling, response generation |
| Telephony | **Twilio** | Phone number, Media Streams, SMS confirmations |
| Speech-to-text | **Deepgram** | Real-time transcription with medical vocabulary |
| Text-to-speech | **Cartesia** | Low-latency natural voice output |
| Voice pipeline | **Pipecat** | STT → LLM → TTS orchestration |

### Tool contract (functions exposed to Claude)

| Tool | What it does |
|---|---|
| `get_patient_record(phone)` | Fetches history, last visit, meds, upcoming appt |
| `get_open_slots(date_range)` | Lists available 30-min slots (9am–5pm, weekdays) |
| `book_appointment(patient_id, slot)` | Creates Google Calendar event |
| `reschedule_appointment(event_id, slot)` | Moves existing appointment |
| `cancel_appointment(event_id)` | Cancels appointment |
| `send_sms_confirmation(patient_id, msg)` | Sends Twilio SMS |
| `log_call_summary(patient_id, summary)` | Writes summary to patient memory |

---

## Setup

### Prerequisites

- Python 3.11+
- [Tencent EdgeOne Makers](https://console.tencentcloud.com/edgeone/makers/new?template=claude-agent-starter-python) account (deploy via `claude-agent-starter-python` template)
- Twilio account with a voice-capable number
- Anthropic API key
- Deepgram API key
- Google Cloud project with Calendar API enabled

### Install

```bash
git clone https://github.com/your-org/sonder
cd sonder
bash setup.sh        # creates venv, installs deps, handles onnxruntime workaround
```

### Configure

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Twilio
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxx
TWILIO_PHONE_NUMBER=+15550001000
TEST_CALL_TO_NUMBER=+15550001234

# Anthropic
ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxx

# Deepgram
DEEPGRAM_API_KEY=xxxxxxxxxxxx

# Google Calendar
GOOGLE_CALENDAR_ID=primary

# Public URL (ngrok or EdgeOne deployment URL)
PUBLIC_BASE_URL=https://your-deployment.edgeone.app
```

### Google Calendar auth (one-time)

```bash
python3 -m app.google_auth_setup
```

### Seed demo patients

```bash
python3 -m app.seed_patients
```

This creates three pre-loaded patients (Maria Chen, James Okafor, Priya Sharma) mapped to phone numbers you control.

### Run locally

```bash
source venv/bin/activate
uvicorn app.server:app --reload --port 8000
```

Open `http://localhost:8000` for the live dashboard.

Expose locally with ngrok:

```bash
ngrok http 8000
# set PUBLIC_BASE_URL in .env to the ngrok https URL
```

Point your Twilio number's voice webhook to `https://your-ngrok-url/twiml/inbound`.

### Deploy to EdgeOne

```bash
# Using the claude-agent-starter-python template
edgeone deploy
```

---

## Dashboard

`/` — landing page + live dashboard

- **Patients panel** — full profiles, edit in-place, add/delete
- **Calls panel** — live call log, real-time transcript, AI-generated call summaries
- **Stats bar** — patients, total calls, active calls (live indicator), appointments booked
- **Place call** — trigger an outbound test call directly from the UI

---

## Project structure

```
sonder/
├── app/
│   ├── server.py          # FastAPI: Twilio webhooks, REST API, WebSocket
│   ├── bot.py             # Pipecat pipeline + Claude tool-calling
│   ├── memory_store.py    # SQLite: patients + calls
│   ├── calendar_tools.py  # Google Calendar API wrapper
│   ├── seed_patients.py   # Demo patient seeding
│   ├── google_auth_setup.py
│   └── static/
│       └── index.html     # Landing page + dashboard (single file)
├── credentials/
│   └── client_secret.json # Google OAuth credentials (not committed)
├── sonder.db              # SQLite database
├── requirements.txt
├── setup.sh
└── .env                   # Secrets (not committed)
```

---

## MVP scope

- 3–5 seeded demo patients (no patient onboarding flow)
- Single active call at a time (no concurrency handling)
- Scheduling and FAQ only — agent will not attempt clinical advice
- No HIPAA compliance (production path documented, not built)

---

## Built at

**MiniHack · July 2026** — Deployed on Tencent EdgeOne Makers using the `claude-agent-starter-python` template.
