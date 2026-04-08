"""
STT API

REST  POST /stt/transcribe  - 오디오 파일 업로드 → 텍스트 반환 (로컬 테스트용)
WS    WS   /stt/ws          - 오디오 청크 스트리밍 → 실시간 텍스트 반환 (키오스크 연동용)
"""

import json
import tempfile
from collections import deque
from pathlib import Path

import numpy as np
from fastapi import APIRouter, File, Query, UploadFile, WebSocket, WebSocketDisconnect

from voice.stt import load_model, transcribe, transcribe_array

router = APIRouter(prefix="/stt", tags=["stt"])

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}

# VAD 파라미터 (stt_realtime.py와 동일)
SAMPLE_RATE = 16000
ENERGY_THRESHOLD = 0.005
SPEECH_PAD_CHUNKS = 4
SILENCE_CHUNKS = 16
MIN_SPEECH_CHUNKS = 6

_model = None


def get_model():
    global _model
    if _model is None:
        _model = load_model(model_size="small", device="cpu")
    return _model


def rms(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(chunk ** 2)))


# ── REST ──────────────────────────────────────────────────────

@router.post("/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str = Query(default="ko"),
):
    """
    오디오 파일을 받아 텍스트로 변환합니다. (로컬 테스트용)
    Swagger UI(/docs)에서 파일을 업로드해 바로 테스트할 수 있습니다.
    """
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=400,
            detail=f"지원 형식: {', '.join(SUPPORTED_EXTENSIONS)}",
        )

    contents = await file.read()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(contents)
        tmp_path = tmp.name

    try:
        text = transcribe(get_model(), tmp_path, language=language)
    finally:
        Path(tmp_path).unlink(missing_ok=True)

    return {"text": text, "language": language}


# ── WebSocket ─────────────────────────────────────────────────

@router.websocket("/ws")
async def stt_websocket(websocket: WebSocket):
    """
    실시간 STT WebSocket 엔드포인트. (키오스크 브라우저 연동용)

    클라이언트는 float32 PCM 바이트를 50ms 청크 단위로 전송합니다.
    서버는 발화가 끝날 때마다 JSON으로 인식 결과를 반환합니다.

    반환 형식: {"text": "인식된 텍스트"}
    """
    await websocket.accept()
    model = get_model()

    pre_roll: deque[np.ndarray] = deque(maxlen=SPEECH_PAD_CHUNKS)
    speech_buffer: list[np.ndarray] = []
    silence_count = 0
    in_speech = False

    try:
        while True:
            raw = await websocket.receive_bytes()
            chunk = np.frombuffer(raw, dtype=np.float32)

            is_voice = rms(chunk) > ENERGY_THRESHOLD

            if not in_speech:
                pre_roll.append(chunk)
                if is_voice:
                    in_speech = True
                    silence_count = 0
                    speech_buffer = list(pre_roll)
            else:
                speech_buffer.append(chunk)
                if is_voice:
                    silence_count = 0
                else:
                    silence_count += 1
                    if silence_count >= SILENCE_CHUNKS:
                        if len(speech_buffer) >= MIN_SPEECH_CHUNKS:
                            audio = np.concatenate(speech_buffer)
                            text = transcribe_array(model, audio)
                            if text.strip():
                                await websocket.send_text(
                                    json.dumps({"text": text.strip()}, ensure_ascii=False)
                                )
                        speech_buffer = []
                        silence_count = 0
                        in_speech = False
                        pre_roll.clear()

    except WebSocketDisconnect:
        pass
