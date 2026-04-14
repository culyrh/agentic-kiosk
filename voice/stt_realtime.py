"""
실시간 STT 모듈
마이크로 입력되는 음성을 실시간으로 감지해 텍스트로 변환

흐름:
  마이크 스트림 → 음성 구간 감지 (에너지 기반) → faster-whisper 인식 → on_result 콜백

사용:
  python voice/stt_realtime.py
  python voice/stt_realtime.py --model small --device cpu
  python voice/stt_realtime.py --api-url http://localhost:8000  # 인식 결과를 API 서버로 전송
"""

import argparse
import time
from collections import deque
from typing import Callable

import numpy as np
import sounddevice as sd

from voice.stt import load_model, transcribe_array


# ── 기본 파라미터 ──────────────────────────────────────────────
SAMPLE_RATE = 16000       # Whisper 권장 샘플레이트
CHANNELS = 1
CHUNK_DURATION = 0.05     # 한 번에 읽을 청크 길이 (초)
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION)

ENERGY_THRESHOLD = 0.005   # 음성/무음 판단 RMS 임계값 (환경에 따라 조정)
SPEECH_PAD_CHUNKS = 4     # 음성 시작 전 유지할 pre-roll 청크 수
SILENCE_CHUNKS = 16       # 무음이 이 청크 수 이상 지속되면 발화 종료로 판단 (약 0.8초)
MIN_SPEECH_CHUNKS = 6     # 최소 이 청크 수 이상이어야 인식 시도 (너무 짧은 잡음 무시)


def rms(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(chunk ** 2)))


def listen_once(model, language: str = "ko", timeout: float = 30.0) -> str | None:
    """
    마이크에서 한 발화를 듣고 텍스트를 반환합니다.
    발화가 끝나면 즉시 반환합니다.

    Args:
        model: load_model()로 생성한 WhisperModel
        language: 언어 코드
        timeout: 발화 시작을 기다리는 최대 시간 (초). 초과하면 None 반환.

    Returns:
        인식된 텍스트. 발화 없으면 None.
    """
    pre_roll: deque[np.ndarray] = deque(maxlen=SPEECH_PAD_CHUNKS)
    speech_buffer: list[np.ndarray] = []
    silence_count = 0
    in_speech = False
    wait_start = time.time()

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        blocksize=CHUNK_SAMPLES,
    ) as stream:
        while True:
            chunk, _ = stream.read(CHUNK_SAMPLES)
            chunk = chunk[:, 0]

            energy = rms(chunk)
            is_voice = energy > ENERGY_THRESHOLD

            if not in_speech:
                if time.time() - wait_start > timeout:
                    return None
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
                            return transcribe_array(model, audio, language=language)
                        return None


def listen(model, language: str = "ko", on_result: Callable[[str], None] = None):
    """
    마이크에서 실시간으로 음성을 받아 STT 처리.

    Args:
        model: load_model()로 생성한 WhisperModel
        language: 언어 코드
        on_result: 인식된 텍스트를 받는 콜백 함수. None이면 print로 출력.
    """
    print("[실시간 STT] 마이크 대기 중... (Ctrl+C로 종료)\n")

    pre_roll = deque(maxlen=SPEECH_PAD_CHUNKS)  # 음성 직전 청크 버퍼
    speech_buffer: list[np.ndarray] = []
    silence_count = 0
    in_speech = False

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        blocksize=CHUNK_SAMPLES,
    ) as stream:
        while True:
            chunk, _ = stream.read(CHUNK_SAMPLES)
            chunk = chunk[:, 0]  # mono

            energy = rms(chunk)
            is_voice = energy > ENERGY_THRESHOLD

            if not in_speech:
                pre_roll.append(chunk)
                if is_voice:
                    in_speech = True
                    silence_count = 0
                    speech_buffer = list(pre_roll)  # pre-roll 포함해서 시작
            else:
                speech_buffer.append(chunk)
                if is_voice:
                    silence_count = 0
                else:
                    silence_count += 1
                    if silence_count >= SILENCE_CHUNKS:
                        # ── 발화 종료 → 인식 실행 ──
                        if len(speech_buffer) >= MIN_SPEECH_CHUNKS:
                            audio = np.concatenate(speech_buffer)
                            start = time.time()
                            result = transcribe_array(model, audio, language=language)
                            elapsed = time.time() - start

                            if result.strip():
                                print(f"[인식] {result.strip()}")
                                print(f"      ({elapsed:.2f}초)\n")
                                if on_result:
                                    on_result(result.strip())

                        # 상태 초기화
                        speech_buffer = []
                        silence_count = 0
                        in_speech = False
                        pre_roll.clear()


def _make_api_callback(api_url: str) -> Callable[[str], None]:
    """인식된 텍스트를 API 서버의 /stt/process로 전송하는 콜백을 반환합니다."""
    import urllib.request
    import urllib.error
    import json

    endpoint = f"{api_url.rstrip('/')}/stt/process"

    def callback(text: str):
        payload = json.dumps({"text": text}).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                results = body.get("results", [])
                if results:
                    print("[검색 결과]")
                    for r in results:
                        print(f"  - {r['content'][:60]}  (score: {r['score']})")
                    print()
        except urllib.error.URLError as e:
            print(f"[API 오류] {e}\n")

    return callback


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="small", choices=["tiny", "small", "medium", "large-v3"])
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--language", default="ko")
    parser.add_argument("--threshold", type=float, default=ENERGY_THRESHOLD,
                        help="음성 감지 RMS 임계값 (기본 0.01, 주변 소음 많으면 높여서 조정)")
    parser.add_argument("--api-url", default=None,
                        help="인식 결과를 전송할 API 서버 URL (예: http://localhost:8000)")
    args = parser.parse_args()

    ENERGY_THRESHOLD = args.threshold

    on_result = _make_api_callback(args.api_url) if args.api_url else None

    model = load_model(model_size=args.model, device=args.device)

    try:
        listen(model, language=args.language, on_result=on_result)
    except KeyboardInterrupt:
        print("\n[종료]")
