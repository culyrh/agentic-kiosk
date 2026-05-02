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
import time
from collections import deque
from pathlib import Path

import numpy as np
import torch
from fastapi import APIRouter, File, Query, UploadFile, WebSocket, WebSocketDisconnect
from silero_vad import load_silero_vad

from app.agent import chat
from voice.stt import load_model, transcribe, transcribe_array
from voice.tts import synthesize
from db.sqlite import get_menu_by_name

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


def split_response(text: str) -> tuple[str, str | list, str, str]:
    """에이전트 응답에서 [REFINED], [ACTION], [SCREEN] 태그를 파싱해 분리"""
    refined_match = re.search(r'\[REFINED\](.*?)\[/REFINED\]', text, re.DOTALL)
    refined = refined_match.group(1).strip() if refined_match else ""
    text = re.sub(r'\[REFINED\].*?\[/REFINED\]', '', text, flags=re.DOTALL)

    action_match = re.search(r'\[ACTION\](.*?)\[/ACTION\]', text, re.DOTALL)
    action = action_match.group(1).strip() if action_match else "NONE"
    text = re.sub(r'\[ACTION\].*?\[/ACTION\]', '', text, flags=re.DOTALL)

    screen_matches = re.findall(r'\[SCREEN\](.*?)\[/SCREEN\]', text, re.DOTALL)
    voice = re.sub(r'\[SCREEN\].*?\[/SCREEN\]', '', text, flags=re.DOTALL).strip()
    screen_text = screen_matches[0].strip() if screen_matches else ""

    items = []
    for line in screen_text.splitlines():
        name = re.sub(r'\s*\(.*?\)\s*$', '', line.lstrip('-•0123456789. ').strip())
        if not name:
            continue
        row = get_menu_by_name(name)
        if row:
            items.append({"name": row["name"], "price": row["price"], "img_url": row["img_url"]})

    screen = items if items else [line for line in screen_text.splitlines() if line.strip()]
    return voice, screen, action, refined


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

# 타임아웃 설정
INACTIVITY_TIMEOUT = 180  # 3분

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
    last_activity_time = time.time()  # ← 마지막 활동 시간 기록

    # 동일 세션에서 파이프라인이 동시에 실행되면 conversation_history에 race condition 발생
    # (ToolMessage가 preceding tool_calls 없이 삽입됨 → OpenAI 400 에러)
    # Lock으로 직렬화해 한 번에 하나의 파이프라인만 실행되도록 보장
    pipeline_lock = asyncio.Lock()

    async def process_and_send(audio: np.ndarray):
        # STT → 정제 → 에이전트를 순차 실행하되, asyncio.to_thread로 동기 함수를 별도
        # 스레드에서 실행해 이벤트 루프를 블로킹하지 않음
        # pipeline_lock으로 감싸 동시 실행을 막고 히스토리 race condition 방지
        nonlocal last_activity_time
        async with pipeline_lock:
            stt_text = await asyncio.to_thread(transcribe_array, model, audio)
            if not stt_text.strip():
                return
            last_activity_time = time.time()  # ← 발화 감지 시 갱신

            # 욕설 필터링 (1차 필터링과 동일한 함수 재사용)
            from api.main import contains_blocked_keyword
            if contains_blocked_keyword(stt_text.strip()):
                await websocket.send_text(
                    json.dumps({
                        "stt_text": stt_text.strip(),
                        "voice": "부적절한 표현이 포함되어 있습니다.",
                        "screen": "",
                        "action": "NONE",
                    }, ensure_ascii=False)
                )
                return

            response = await asyncio.to_thread(chat, stt_text.strip(), session_id)
            voice, screen, action, refined = split_response(response)
            await websocket.send_text(
                json.dumps({
                    "stt_text": stt_text.strip(),
                    "refined_text": refined or stt_text.strip(),
                    "voice": voice,
                    "screen": screen,
                    "action": action,
                }, ensure_ascii=False)
            )
            # JSON 직후 TTS 오디오를 binary frame으로 전송 → 프론트가 받아서 바로 재생
            if voice:
                audio_bytes = await asyncio.to_thread(synthesize, voice)
                await websocket.send_bytes(audio_bytes)

    async def check_inactivity():
        """3분 비활성 시 장바구니 + 히스토리 초기화"""
        while True:
            await asyncio.sleep(30)  # 30초마다 체크
            if time.time() - last_activity_time > INACTIVITY_TIMEOUT:
                from db.sqlite import clear_cart
                from app.agent import clear_history
                clear_cart(session_id)
                clear_history(session_id)
                # 프론트에 초기화 알림
                try:
                    await websocket.send_text(
                        json.dumps({
                            "stt_text": "",
                            "voice": "일정 시간 동안 이용이 없어 초기화되었습니다.",
                            "screen": "",
                            "action": "TIMEOUT",
                        }, ensure_ascii=False)
                    )
                except:
                    pass

    try:
        # 타임아웃 체크 백그라운드 태스크 시작
        asyncio.create_task(check_inactivity())
        
        while True:
            raw = await websocket.receive()

            # 터치 신호면 활동 시간만 갱신하고 넘어감
            if raw.get("text"):
                try:
                    data = json.loads(raw["text"])
                    if data.get("type") == "touch":
                        last_activity_time = time.time()
                except:
                    pass
                continue

            # 오디오 청크 처리 (기존 VAD 로직)
            if not raw.get("bytes"):
                continue

            chunk = np.frombuffer(raw["bytes"], dtype=np.float32)
            is_voice = rms(chunk) > ENERGY_THRESHOLD

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

    except (WebSocketDisconnect, RuntimeError):
        from db.sqlite import clear_cart
        from app.agent import clear_history
        clear_cart(session_id)
        clear_history(session_id)
