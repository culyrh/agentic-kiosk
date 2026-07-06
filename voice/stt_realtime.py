"""
실시간 STT 모듈 (Silero VAD)
마이크로 입력되는 음성을 실시간으로 감지해 텍스트로 변환

흐름:
  마이크 스트림 → Silero VAD → faster-whisper 인식 → on_result 콜백

사용:
  python voice/stt_realtime.py
  python voice/stt_realtime.py --model small --device cpu
  python voice/stt_realtime.py --api-url http://localhost:8000
"""

import argparse
import time
from typing import Callable

import numpy as np
import sounddevice as sd

from voice.stt import load_model, transcribe_array
from voice.vad_silero import CHUNK_SIZE, SAMPLE_RATE, StreamingVAD

CHANNELS = 1


def listen_once(model, language: str = "ko", timeout: float = 30.0) -> str | None:
    """마이크에서 한 발화를 듣고 텍스트를 반환. timeout 초 내 발화 없으면 None."""
    vad = StreamingVAD()
    wait_start = time.time()

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        blocksize=CHUNK_SIZE,
    ) as stream:
        while True:
            if not vad.in_speech and time.time() - wait_start > timeout:
                return None

            chunk, _ = stream.read(CHUNK_SIZE)
            utterance = vad.feed(chunk[:, 0])
            if utterance is not None:
                return transcribe_array(model, utterance, language=language)


def listen(model, language: str = "ko", on_result: Callable[[str], None] = None):
    """마이크에서 실시간으로 음성을 받아 STT 처리. Ctrl+C로 종료."""
    print("[실시간 STT] 마이크 대기 중... (Ctrl+C로 종료)\n")

    vad = StreamingVAD()

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="float32",
        blocksize=CHUNK_SIZE,
    ) as stream:
        while True:
            chunk, _ = stream.read(CHUNK_SIZE)
            utterance = vad.feed(chunk[:, 0])

            if utterance is None:
                continue

            start = time.time()
            result = transcribe_array(model, utterance, language=language)
            elapsed = time.time() - start

            if result.strip():
                print(f"[인식] {result.strip()}")
                print(f"      ({elapsed:.2f}초)\n")
                if on_result:
                    on_result(result.strip())


def _make_api_callback(api_url: str) -> Callable[[str], None]:
    import json
    import urllib.error
    import urllib.request

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
    parser.add_argument("--threshold", type=float, default=0.5,
                        help="Silero VAD 확률 임계값 (기본 0.5)")
    parser.add_argument("--api-url", default=None,
                        help="인식 결과를 전송할 API 서버 URL (예: http://localhost:8000)")
    args = parser.parse_args()

    on_result = _make_api_callback(args.api_url) if args.api_url else None
    model = load_model(model_size=args.model, device=args.device)

    try:
        listen(model, language=args.language, on_result=on_result)
    except KeyboardInterrupt:
        print("\n[종료]")
