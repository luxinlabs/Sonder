#!/usr/bin/env bash
# Sonder setup.
#
# pipecat-ai 1.4.0 unconditionally requires onnxruntime~=1.24.3, whose wheels
# only target macOS 14+. On macOS 13 (Ventura) that pin is unsatisfiable, even
# though Silero VAD works fine against onnxruntime 1.23.2 in practice. So we
# install pipecat-ai with --no-deps and bring in its real dependencies
# ourselves, pinned to the last onnxruntime that has a Ventura wheel.
#
# STT needs Deepgram (cloud): pipecat-ai's whisper/stt.py module unconditionally
# imports mlx_whisper on any Darwin arm64 host, and mlx refuses to load below
# macOS 13.5 -- there is no local-STT path on an older Apple Silicon Mac
# through pipecat. TTS defaults to Piper (local, no account); set
# CARTESIA_API_KEY in .env to use Cartesia instead.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v ffmpeg >/dev/null; then
  echo "Installing ffmpeg (required to build the 'av' package, used by Piper)..."
  brew install ffmpeg
fi

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q

pip install --no-deps -q "pipecat-ai[websocket,deepgram,piper,anthropic]==1.4.0"

pip install -q \
  onnxruntime==1.23.2 \
  aiofiles aiohttp audioop-lts docstring_parser loguru Markdown nltk "numpy<3" \
  Pillow protobuf pydantic pyloudnorm resampy soxr openai typing_extensions \
  numba websockets pyyaml "pyyaml-include==1.4.1" \
  "anthropic>=0.49.0,<1" "deepgram-sdk>=6.1.1,<8" \
  "piper-tts>=1.3.0,<2" "requests>=2.32.5,<3" \
  "fastapi>=0.115.6,<1" "uvicorn[standard]" python-dotenv twilio \
  google-auth google-auth-oauthlib google-api-python-client

python3 -c "from pipecat.audio.vad.silero import SileroVADAnalyzer; SileroVADAnalyzer(); print('Sonder environment OK')"
