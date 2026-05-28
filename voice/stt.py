"""
STT (Speech-to-Text) 모듈 — OpenAI Whisper API 버전

로컬 faster-whisper 대신 OpenAI의 whisper-1 API를 사용합니다.
OPENAI_API_KEY 환경변수(.env)가 필요합니다.

함수 시그니처는 로컬 버전과 동일하게 유지되어 api/routes/stt.py 수정 불필요.
"""

import io
import os
import wave
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

load_dotenv()

# python run.py debug 로 실행 시 활성화
_DEBUG_RECORD = os.environ.get("STT_DEBUG", "0") == "1"
_DEBUG_DIR = Path("tests/debug_audio")
_debug_counter = 0


def _save_debug_wav(audio: np.ndarray, label: str) -> None:
    """trimmed 오디오를 WAV로 저장. STT_DEBUG=1 일 때만 호출됨."""
    global _debug_counter
    _debug_counter += 1
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    import re
    safe_label = re.sub(r'[\\/:*?"<>|]', '', label).replace(" ", "_")[:30]
    filename = _DEBUG_DIR / f"{_debug_counter:03d}_{len(audio)/16000:.2f}s_{safe_label}.wav"

    pcm = (audio * 32767).astype(np.int16)
    with wave.open(str(filename), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(pcm.tobytes())
    print(f"[STT] 저장: {filename.name}")


_TRIM_FRAME = 512
_TRIM_THRESHOLD = 0.01
_TRIM_PAD = 1600

_HALLUCINATIONS = {
    "z", "zz", "zzz",
    ".", "..", "...", "....",
    "thank you", "thanks",
    "mbc", "kbs", "sbs",
    "♪", "♫", "(음악)",
    "자막 제공", "번역",
}


def _trim_silence(audio: np.ndarray) -> np.ndarray:
    energies = np.array([
        np.sqrt(np.mean(audio[i: i + _TRIM_FRAME] ** 2))
        for i in range(0, len(audio), _TRIM_FRAME)
    ])
    voiced = np.where(energies > _TRIM_THRESHOLD)[0]
    if len(voiced) == 0:
        return audio
    start = max(0, voiced[0] * _TRIM_FRAME - _TRIM_PAD)
    end = min(len(audio), (voiced[-1] + 1) * _TRIM_FRAME + _TRIM_PAD)
    return audio[start:end]


def _numpy_to_wav_bytes(audio: np.ndarray) -> io.BytesIO:
    """float32 numpy 배열 → WAV 포맷 BytesIO (OpenAI API 전송용)."""
    pcm = (audio * 32767).astype(np.int16)
    buf = io.BytesIO()
    buf.name = "audio.wav"   # OpenAI SDK가 확장자로 포맷 판단
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(pcm.tobytes())
    buf.seek(0)
    return buf


# OpenAI 클라이언트 — 첫 호출 시 초기화 (load_dotenv 이후 보장)
_openai_client = None


def _get_client():
    global _openai_client
    if _openai_client is None:
        from openai import OpenAI
        _openai_client = OpenAI()
    return _openai_client


# ── 공개 인터페이스 (api/routes/stt.py 와 동일한 시그니처 유지) ──────────────

def load_model(model_size: str = "small", device: str = "cpu"):
    """
    로컬 버전 호환용. OpenAI API 버전에서는 모델 로드 불필요.
    None을 반환하며, 이후 transcribe* 함수에서 model 인자는 무시됩니다.
    """
    print("[STT] OpenAI Whisper API 모드 — 로컬 모델 로드 생략")
    _get_client()   # API 키 유효성 미리 체크
    print("[STT] OpenAI 클라이언트 초기화 완료")
    return None


def transcribe(model, audio_path: str, language: str = "ko") -> str:
    """
    오디오 파일 경로 → 텍스트 변환 (REST 엔드포인트용).
    """
    with open(audio_path, "rb") as f:
        response = _get_client().audio.transcriptions.create(
            model="whisper-1",
            file=f,
            language=language,
        )
    return response.text.strip()


def transcribe_array(model, audio: np.ndarray, language: str = "ko") -> str:
    """
    numpy 배열(float32, 16kHz) → 텍스트 변환 (WebSocket 실시간용).
    """
    trimmed = _trim_silence(audio.astype(np.float32))
    print(f"[STT] audio={len(audio)/16000:.2f}s → trimmed={len(trimmed)/16000:.2f}s")

    if len(trimmed) < 16000 * 0.5:
        print(f"[STT] skip: too short ({len(trimmed)/16000:.2f}s)")
        return ""

    wav_buf = _numpy_to_wav_bytes(trimmed)

    response = _get_client().audio.transcriptions.create(
        model="whisper-1",
        file=wav_buf,
        language=language,
    )
    text = response.text.strip()

    if text.lower() in _HALLUCINATIONS:
        print(f"[STT] hallucination filtered: '{text}'")
        if _DEBUG_RECORD:
            _save_debug_wav(trimmed, f"HALLUCINATION_{text}")
        return ""

    if _DEBUG_RECORD:
        _save_debug_wav(trimmed, text or "EMPTY")

    return text


# 단독 실행 테스트: python voice/stt.py test.wav
if __name__ == "__main__":
    import sys
    import time
    from datetime import datetime

    audio_file = sys.argv[1] if len(sys.argv) > 1 else "test.wav"

    print("[STT] OpenAI Whisper API 테스트")
    load_model()

    start = time.time()
    result = transcribe(None, audio_file)
    elapsed = time.time() - start

    print(f"\n[파일]    {audio_file}")
    print(f"[처리시간] {elapsed:.2f}초")
    print(f"[인식결과] {result}")

    output_dir = Path("tests/results")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    audio_name = Path(audio_file).stem
    output_file = output_dir / f"{audio_name}_whisper-api_{timestamp}.txt"

    content = f"모델: whisper-api\n파일: {audio_file}\n처리시간: {elapsed:.2f}초\n\n{result}"
    output_file.write_text(content, encoding="utf-8")
    print(f"\n[저장 완료] {output_file}")
