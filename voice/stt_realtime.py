"""
실시간 STT 모듈
마이크로 입력되는 음성을 실시간으로 감지해 텍스트로 변환

흐름:
  마이크 스트림 → 음성 구간 감지 (에너지 기반) → faster-whisper 인식 → 텍스트 출력

사용:
  python voice/stt_realtime.py
  python voice/stt_realtime.py --model small --device cpu
"""

import argparse
import time
from collections import deque

import numpy as np
import sounddevice as sd

from voice.stt import load_model, transcribe_array


# ── 기본 파라미터 ──────────────────────────────────────────────
SAMPLE_RATE = 16000       # Whisper 권장 샘플레이트
CHANNELS = 1
CHUNK_DURATION = 0.05     # 한 번에 읽을 청크 길이 (초)
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_DURATION)

ENERGY_THRESHOLD = 0.01   # 음성/무음 판단 RMS 임계값 (환경에 따라 조정)
SPEECH_PAD_CHUNKS = 4     # 음성 시작 전 유지할 pre-roll 청크 수
SILENCE_CHUNKS = 16       # 무음이 이 청크 수 이상 지속되면 발화 종료로 판단 (약 0.8초)
MIN_SPEECH_CHUNKS = 6     # 최소 이 청크 수 이상이어야 인식 시도 (너무 짧은 잡음 무시)


def rms(chunk: np.ndarray) -> float:
    return float(np.sqrt(np.mean(chunk ** 2)))


def listen(model, language: str = "ko"):
    """마이크에서 실시간으로 음성을 받아 STT 처리"""
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

                        # 상태 초기화
                        speech_buffer = []
                        silence_count = 0
                        in_speech = False
                        pre_roll.clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="small", choices=["tiny", "small", "medium", "large-v3"])
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--language", default="ko")
    parser.add_argument("--threshold", type=float, default=ENERGY_THRESHOLD,
                        help="음성 감지 RMS 임계값 (기본 0.01, 주변 소음 많으면 높여서 조정)")
    args = parser.parse_args()

    ENERGY_THRESHOLD = args.threshold

    model = load_model(model_size=args.model, device=args.device)

    try:
        listen(model, language=args.language)
    except KeyboardInterrupt:
        print("\n[종료]")
