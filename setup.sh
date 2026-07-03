#!/usr/bin/env bash
# Sonder setup.
#
# pipecat-ai 1.4.0 unconditionally requires onnxruntime~=1.24.3, whose wheels
# only target macOS 14+. On macOS 13 (Ventura) that pin is unsatisfiable, even
# though Silero VAD works fine against onnxruntime 1.23.2 in practice. So we
# install pipecat-ai with --no-deps and bring in its real dependencies
# ourselves, pinned to the last onnxruntime that has a Ventura wheel.
#
# STT/TTS run fully local (Whisper MLX + Piper) -- no Deepgram/Cartesia/etc.
# accounts needed. This requires ffmpeg (for the `av` package) and only works
# on Apple Silicon (mlx-whisper). On other platforms, swap WhisperSTTServiceMLX
# in app/bot.py for WhisperSTTService (faster-whisper, CPU/CUDA).
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v ffmpeg >/dev/null; then
  echo "Installing ffmpeg (required to build the 'av' package)..."
  brew install ffmpeg
fi

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q

pip install --no-deps -q "pipecat-ai[websocket,whisper,mlx-whisper,piper,anthropic]==1.4.0"

pip install -q \
  onnxruntime==1.23.2 \
  aiofiles aiohttp audioop-lts docstring_parser loguru Markdown nltk "numpy<3" \
  Pillow protobuf pydantic pyloudnorm resampy soxr openai typing_extensions \
  numba websockets pyyaml "pyyaml-include==1.4.1" \
  "anthropic>=0.49.0,<1" \
  faster-whisper~=1.2.1 mlx-whisper~=0.4.2 "piper-tts>=1.3.0,<2" "requests>=2.32.5,<3" \
  "fastapi>=0.115.6,<1" "uvicorn[standard]" python-dotenv twilio \
  google-auth google-auth-oauthlib google-api-python-client

python3 -c "from pipecat.audio.vad.silero import SileroVADAnalyzer; SileroVADAnalyzer(); print('Sonder environment OK')"
