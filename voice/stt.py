"""
STT (Speech-to-Text) 모듈
Qwen3-ASR-0.6B를 사용해 로컬에서 음성 → 텍스트 변환

모델은 처음 실행 시 허깅페이스 허브에서 자동 다운로드됩니다.
캐시 위치: C:/Users/사용자/.cache/huggingface/hub/
"""

import numpy as np
import torch
from qwen_asr import Qwen3ASRModel

MODEL_ID = "Qwen/Qwen3-ASR-0.6B"

_LANG_MAP = {"ko": "Korean", "en": "English", "zh": "Chinese", "ja": "Japanese"}

def _lang(code: str) -> str:
    return _LANG_MAP.get(code.lower(), code)


def load_model(model_size: str = MODEL_ID, device: str = "cpu"):
    """
    Qwen3-ASR 모델을 로드합니다.

    Args:
        model_size: HuggingFace 모델 ID 또는 로컬 경로 (기본: Qwen/Qwen3-ASR-0.6B)
        device: "cpu" 또는 "cuda"
    """
    dtype = torch.float16 if device == "cuda" else torch.float32

    print(f"[STT] 모델 로딩: {model_size} / {device}")
    model = Qwen3ASRModel.from_pretrained(model_size, dtype=dtype, device_map=device)
    print("[STT] 모델 로딩 완료")
    return model


def transcribe(model, audio_path: str, language: str = "ko") -> str:
    """
    음성 파일을 텍스트로 변환합니다.

    Args:
        model: load_model()로 생성한 Qwen3ASRModel
        audio_path: 오디오 파일 경로
        language: 언어 코드 ("ko" = 한국어)

    Returns:
        인식된 텍스트 문자열
    """
    results = model.transcribe(audio=audio_path, language=_lang(language))
    return results[0].text if results else ""


def transcribe_array(model, audio: np.ndarray, language: str = "ko") -> str:
    """
    numpy 배열(float32, 16kHz)을 텍스트로 변환합니다.

    Args:
        model: load_model()로 생성한 Qwen3ASRModel
        audio: float32 numpy 배열 (shape: [samples], 16kHz mono)
        language: 언어 코드 ("ko" = 한국어)

    Returns:
        인식된 텍스트 문자열
    """
    results = model.transcribe(audio=(audio.astype(np.float32), 16000), language=_lang(language))
    return results[0].text if results else ""


# 단독 실행 테스트: python voice/stt.py test.wav
if __name__ == "__main__":
    import sys
    import time

    audio_file = sys.argv[1] if len(sys.argv) > 1 else "test.wav"

    model = load_model()

    start = time.time()
    result = transcribe(model, audio_file)
    elapsed = time.time() - start

    print(f"\n[모델]    {MODEL_ID}")
    print(f"[파일]    {audio_file}")
    print(f"[처리시간] {elapsed:.2f}초")
    print(f"[인식결과] {result}")
