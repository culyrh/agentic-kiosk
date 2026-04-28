#/api/routes/stt.py

"""
STT API

REST  POST /stt/transcribe  - 오디오 파일 업로드 → 텍스트 반환 (로컬 테스트용)
WS    WS   /stt/ws          - 오디오 청크 스트리밍 → 실시간 텍스트 반환 (키오스크 연동용)
"""

import asyncio
import json
import re
import tempfile
from collections import deque
from pathlib import Path

import numpy as np
import torch
from fastapi import APIRouter, File, Query, UploadFile, WebSocket, WebSocketDisconnect
from silero_vad import load_silero_vad

from app.refine import refine_stt
from app.agent import chat
from voice.stt import load_model, transcribe, transcribe_array
from voice.tts import synthesize

router = APIRouter(prefix="/stt", tags=["stt"])

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}

# VAD 파라미터
SAMPLE_RATE = 16000
VAD_THRESHOLD = 0.5       # Silero VAD 음성 판정 확률 임계값
SPEECH_PAD_CHUNKS = 4
SILENCE_CHUNKS = 16
MIN_SPEECH_CHUNKS = 6

_vad_model = None

_model = None


def split_response(text: str) -> tuple[str, str]:
    """에이전트 응답에서 [SCREEN]...[/SCREEN] 태그를 파싱해 음성/화면 내용을 분리"""
    screen_matches = re.findall(r'\[SCREEN\](.*?)\[/SCREEN\]', text, re.DOTALL)
    voice = re.sub(r'\[SCREEN\].*?\[/SCREEN\]', '', text, flags=re.DOTALL).strip()
    screen = screen_matches[0].strip() if screen_matches else ""
    return voice, screen


def get_model():
    global _model
    if _model is None:
        _model = load_model(model_size="small", device="cpu")
    return _model


def get_vad_model():
    global _vad_model
    if _vad_model is None:
        _vad_model = load_silero_vad()
    return _vad_model


def is_speech(chunk: np.ndarray) -> bool:
    # Silero VAD는 512샘플(32ms) 단위 입력을 요구 → 청크 앞부분 512샘플만 사용
    audio = torch.from_numpy(chunk[:512].copy())
    with torch.no_grad():
        prob = get_vad_model()(audio, SAMPLE_RATE).item()
    return prob > VAD_THRESHOLD


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
async def stt_websocket(websocket: WebSocket, session_id: str = "default"):
    """
    실시간 전체 파이프라인 WebSocket 엔드포인트. (키오스크 브라우저 연동용)

    클라이언트는 float32 PCM 바이트를 50ms 청크 단위로 전송합니다.
    발화가 끝나면 STT → LLM 정제 → 에이전트 순으로 처리 후 응답을 반환합니다.

    반환 형식: {"stt_text": "인식된 텍스트", "refined_text": "정제된 텍스트", "response": "에이전트 응답"}
    """
    await websocket.accept()
    model = get_model()
    vad = get_vad_model()
    vad.reset_states()  # 세션마다 Silero 내부 상태 초기화

    # VAD 상태 변수
    pre_roll: deque[np.ndarray] = deque(maxlen=SPEECH_PAD_CHUNKS)  # 발화 시작 직전 청크 버퍼
    speech_buffer: list[np.ndarray] = []
    silence_count = 0
    in_speech = False

    # 동일 세션에서 파이프라인이 동시에 실행되면 conversation_history에 race condition 발생
    # (ToolMessage가 preceding tool_calls 없이 삽입됨 → OpenAI 400 에러)
    # Lock으로 직렬화해 한 번에 하나의 파이프라인만 실행되도록 보장
    pipeline_lock = asyncio.Lock()

    async def process_and_send(audio: np.ndarray):
        # STT → 정제 → 에이전트를 순차 실행하되, asyncio.to_thread로 동기 함수를 별도
        # 스레드에서 실행해 이벤트 루프를 블로킹하지 않음
        # pipeline_lock으로 감싸 동시 실행을 막고 히스토리 race condition 방지
        async with pipeline_lock:
            stt_text = await asyncio.to_thread(transcribe_array, model, audio)
            if not stt_text.strip():
                return
            refined_text = await asyncio.to_thread(refine_stt, stt_text.strip())

            # 욕설 필터링 (1차 필터링과 동일한 함수 재사용)
            from api.main import contains_blocked_keyword
            if contains_blocked_keyword(refined_text):
                await websocket.send_text(
                    json.dumps({
                        "stt_text": stt_text.strip(),
                        "refined_text": refined_text,
                        "voice": "부적절한 표현이 포함되어 있습니다.",
                        "screen": "",
                    }, ensure_ascii=False)
                )
                return   
        
            response = await asyncio.to_thread(chat, refined_text, session_id)
            voice, screen = split_response(response)
            await websocket.send_text(
                json.dumps({
                    "stt_text": stt_text.strip(),
                    "refined_text": refined_text,
                    "voice": voice,
                    "screen": screen,
                }, ensure_ascii=False)
            )
            # JSON 직후 TTS 오디오를 binary frame으로 전송 → 프론트가 받아서 바로 재생
            if voice:
                audio_bytes = await asyncio.to_thread(synthesize, voice)
                await websocket.send_bytes(audio_bytes)

    try:
        while True:
            raw = await websocket.receive_bytes()
            chunk = np.frombuffer(raw, dtype=np.float32)

            is_voice = is_speech(chunk)

            if not in_speech:
                pre_roll.append(chunk)
                if is_voice:
                    in_speech = True
                    silence_count = 0
                    speech_buffer = list(pre_roll)  # pre-roll 포함해서 발화 시작
            else:
                speech_buffer.append(chunk)
                if is_voice:
                    silence_count = 0
                else:
                    silence_count += 1
                    if silence_count >= SILENCE_CHUNKS:  # 무음 0.8초 → 발화 종료
                        if len(speech_buffer) >= MIN_SPEECH_CHUNKS:
                            audio = np.concatenate(speech_buffer)
                            # create_task로 파이프라인을 백그라운드에 띄우고
                            # VAD는 즉시 초기화해서 다음 발화를 바로 감지
                            asyncio.create_task(process_and_send(audio))
                        speech_buffer = []
                        silence_count = 0
                        in_speech = False
                        pre_roll.clear()

    except WebSocketDisconnect:
        pass
