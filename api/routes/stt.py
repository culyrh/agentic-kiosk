#/api/routes/stt.py

"""
STT API

REST  POST /stt/transcribe  - 오디오 파일 업로드 → 텍스트 반환 (로컬 테스트용)
WS    WS   /stt/ws          - 오디오 청크 스트리밍 → 실시간 텍스트 반환 (키오스크 연동용)
"""

import asyncio
import json
import tempfile
import time
from collections import deque
from pathlib import Path

import numpy as np
from fastapi import APIRouter, File, Query, UploadFile, WebSocket, WebSocketDisconnect

from app.agent import AgentResponse, chat
from voice.stt import load_model, transcribe, transcribe_array
from voice.tts import synthesize

router = APIRouter(prefix="/stt", tags=["stt"])

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}

# VAD 파라미터
SAMPLE_RATE = 16000
ENERGY_THRESHOLD = 0.005
SPEECH_PAD_CHUNKS = 4
SILENCE_CHUNKS = 16
MIN_SPEECH_CHUNKS = 6

_model = None


def split_response(text: str) -> tuple[str, str, str, str, str, str]:
    """에이전트 JSON 응답을 파싱해 (voice, screen, action, refined, drink_option, side_option) 반환"""
    try:
        data = AgentResponse.model_validate_json(text)
        return data.voice, data.screen, data.action, data.refined, data.drink_option, data.side_option
    except Exception:
        return text, "", "NONE", "", "", ""


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
        nonlocal last_activity_time
        async with pipeline_lock:
            t0 = time.time()
            stt_text = await asyncio.to_thread(transcribe_array, model, audio)
            t1 = time.time()

            if not stt_text.strip():
                return
            last_activity_time = t1

            from api.main import contains_blocked_keyword
            if contains_blocked_keyword(stt_text.strip()):
                await websocket.send_text(
                    json.dumps({
                        "stt_text": stt_text.strip(),
                        "voice": "부적절한 표현이 포함되어 있습니다.",
                        "screen": "", "action": "NONE",
                    }, ensure_ascii=False)
                )
                return

            from app.agent import chat_stream
            from voice.tts import synthesize_async

            voice_parts = []
            full_response = None
            agent_latency = None
            t_agent_start = time.time()

            async for item in chat_stream(stt_text.strip(), session_id):
                if isinstance(item, tuple) and item[0] == "__done__":
                    full_response, agent_latency = item[1]
                    break
                # 문장 단위 voice → 즉시 TTS 합성 후 전송
                sentence = item
                voice_parts.append(sentence)
                audio_bytes = await synthesize_async(sentence)
                await websocket.send_bytes(audio_bytes)

            t2 = time.time()

            voice, screen, action, refined, drink_option, side_option = split_response(full_response or "")
            full_voice = " ".join(voice_parts) if voice_parts else voice

            latency = {
                "stt_ms":   round((t1 - t0) * 1000),
                "agent_ms": round((t2 - t_agent_start) * 1000),
                "tts_ms":   0,  # streaming 처리로 별도 측정 생략
                "total_ms": round((t2 - t0) * 1000),
                "agent_detail": agent_latency or {},
            }
            ad = agent_latency or {}
            print(
                f"[LATENCY] stt={latency['stt_ms']}ms"
                f" agent={round((t2 - t_agent_start) * 1000)}ms"
                f" (llm={ad.get('llm_total_ms', '?')}ms"
                f" tool={ad.get('tool_total_ms', '?')}ms)"
                f" total={latency['total_ms']}ms"
            )

            # 스트리밍 오디오 전송 후 메타데이터 JSON 전송
            await websocket.send_text(
                json.dumps({
                    "stt_text": stt_text.strip(),
                    "refined_text": refined or stt_text.strip(),
                    "voice": full_voice,
                    "screen": screen,
                    "action": action,
                    "drink_option": drink_option,
                    "side_option": side_option,
                    "latency": latency,
                }, ensure_ascii=False)
            )

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

            # 텍스트 이벤트 처리
            if raw.get("text"):
                try:
                    data = json.loads(raw["text"])
                    if data.get("type") == "touch":
                        last_activity_time = time.time()
                    elif data.get("type") == "payment_complete":
                        from app.tools.cart_tools import confirm_order
                        from app.agent import clear_history
                        from app.session_context import current_session_id
                        payment_method = data.get("payment_method", "카드")
                        current_session_id.set(session_id)
                        result = await asyncio.to_thread(confirm_order.func, payment_method)
                        if "주문이 완료되었습니다" in result:
                            clear_history(session_id)
                            voice_text = "주문이 완료되었습니다. 감사합니다!"
                            audio_bytes = await asyncio.to_thread(synthesize, voice_text)
                            await websocket.send_text(
                                json.dumps({"voice": voice_text, "action": "PAGE:complete"}, ensure_ascii=False)
                            )
                            if audio_bytes:
                                await websocket.send_bytes(audio_bytes)
                        else:
                            print(f"[ERROR] confirm_order 실패: {result}")
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
