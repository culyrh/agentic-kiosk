"""
STT (Speech-to-Text) 모듈
faster-whisper를 사용해 로컬에서 음성 → 텍스트 변환

모델은 처음 실행 시 허깅페이스 허브에서 자동 다운로드됩니다.
캐시 위치: C:/Users/사용자/.cache/huggingface/hub/
"""

import os
import wave
from pathlib import Path

import numpy as np
from faster_whisper import WhisperModel

# python run.py debug 로 실행 시 활성화
_DEBUG_RECORD = os.environ.get("STT_DEBUG", "0") == "1"
_DEBUG_DIR = Path("tests/debug_audio")
_debug_counter = 0


def _save_debug_wav(audio: np.ndarray, label: str) -> None:
    """trimmed 오디오를 WAV로 저장. STT_DEBUG=1 일 때만 호출됨."""
    global _debug_counter
    _debug_counter += 1
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    # Windows 파일명 금지 문자 전부 제거: \ / : * ? " < > |
    import re
    safe_label = re.sub(r'[\\/:*?"<>|]', '', label).replace(" ", "_")[:30]
    filename = _DEBUG_DIR / f"{_debug_counter:03d}_{len(audio)/16000:.2f}s_{safe_label}.wav"

    pcm = (audio * 32767).astype(np.int16)
    with wave.open(str(filename), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)   # int16 = 2 bytes
        wf.setframerate(16000)
        wf.writeframes(pcm.tobytes())
    print(f"[STT] 저장: {filename.name}")

_TRIM_FRAME = 512
_TRIM_THRESHOLD = 0.01   # RMS 기준 무음 판단값
_TRIM_PAD = 1600         # 트리밍 후 앞뒤 여백 (0.1초 @ 16kHz)

# Whisper 환각(hallucination) 패턴 — 이 결과는 빈 문자열로 처리
_HALLUCINATIONS = {
    "z", "zz", "zzz",
    ".", "..", "...", "....",
    "thank you", "thanks",
    "mbc", "kbs", "sbs",      # 자막 환각
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


def load_model(model_size: str = "medium", device: str = "cpu") -> WhisperModel:
    """
    Whisper 모델을 로드합니다.
    처음 실행 시 허깅페이스에서 자동 다운로드 (medium 기준 약 1.5GB).

    Args:
        model_size: "small" / "medium" / "large-v3"
        device: "cpu" 또는 "cuda" (GPU 있을 때)
    """
    compute_type = "float16" if device == "cuda" else "int8"

    print(f"[STT] 모델 로딩: whisper-{model_size} / {device} / {compute_type}")
    model = WhisperModel(model_size, device=device, compute_type=compute_type)
    print("[STT] 모델 로딩 완료")
    return model


def transcribe(model: WhisperModel, audio_path: str, language: str = "ko") -> str:
    """
    음성 파일을 텍스트로 변환합니다.

    Args:
        model: load_model()로 생성한 WhisperModel
        audio_path: 오디오 파일 경로 (.wav, .mp3 등)
        language: 언어 코드 ("ko" = 한국어)

    Returns:
        인식된 텍스트 문자열
    """
    from faster_whisper.audio import decode_audio
    audio = _trim_silence(decode_audio(audio_path))
    segments, _ = model.transcribe(
        audio,
        language=language,
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    text = " ".join(segment.text.strip() for segment in segments)
    return text


def transcribe_array(model: WhisperModel, audio: "np.ndarray", language: str = "ko") -> str:
    """
    numpy 배열(float32, 16kHz)을 텍스트로 변환합니다.
    실시간 마이크 입력처럼 파일 없이 바로 인식할 때 사용합니다.

    Args:
        model: load_model()로 생성한 WhisperModel
        audio: float32 numpy 배열 (shape: [samples], 16kHz mono)
        language: 언어 코드 ("ko" = 한국어)

    Returns:
        인식된 텍스트 문자열
    """
    trimmed = _trim_silence(audio.astype(np.float32))
    print(f"[STT] audio={len(audio)/16000:.2f}s → trimmed={len(trimmed)/16000:.2f}s")

    # 0.5초 미만 오디오는 노이즈 버스트로 판단하고 스킵
    # → 짧은 모호한 오디오가 beam search를 오히려 더 오래 돌리는 문제 방지
    if len(trimmed) < 16000 * 0.5:
        print(f"[STT] skip: too short ({len(trimmed)/16000:.2f}s)")
        return ""

    segments, _ = model.transcribe(
        trimmed,
        language=language,
        beam_size=2,
    )

    text = " ".join(segment.text.strip() for segment in segments)

    # 환각 패턴 필터: 알려진 쓰레기 출력이면 빈 문자열로 처리
    if text.strip().lower() in _HALLUCINATIONS:
        print(f"[STT] hallucination filtered: '{text.strip()}'")
        if _DEBUG_RECORD:
            _save_debug_wav(trimmed, f"HALLUCINATION_{text.strip()}")
        return ""

    if _DEBUG_RECORD:
        _save_debug_wav(trimmed, text.strip() or "EMPTY")

    return text


# 단독 실행 테스트: python voice/stt.py test.wav medium
if __name__ == "__main__":
    import sys
    import time
    from datetime import datetime
    from pathlib import Path

    audio_file = sys.argv[1] if len(sys.argv) > 1 else "test.wav"
    model_size = sys.argv[2] if len(sys.argv) > 2 else "medium"

    model = load_model(model_size=model_size)

    start = time.time()
    result = transcribe(model, audio_file)
    elapsed = time.time() - start

    print(f"\n[모델]    whisper-{model_size}")
    print(f"[파일]    {audio_file}")
    print(f"[처리시간] {elapsed:.2f}초")
    print(f"[인식결과] {result}")

    # tests/results/ 에 결과 저장
    output_dir = Path("tests/results")
    output_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    audio_name = Path(audio_file).stem
    output_file = output_dir / f"{audio_name}_{model_size}_{timestamp}.txt"

    content = f"모델: whisper-{model_size}\n파일: {audio_file}\n처리시간: {elapsed:.2f}초\n\n{result}"
    output_file.write_text(content, encoding="utf-8")
    print(f"\n[저장 완료] {output_file}")
