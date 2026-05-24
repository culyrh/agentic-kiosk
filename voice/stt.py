"""
STT (Speech-to-Text) 모듈
faster-whisper를 사용해 로컬에서 음성 → 텍스트 변환

모델은 처음 실행 시 허깅페이스 허브에서 자동 다운로드됩니다.
캐시 위치: C:/Users/사용자/.cache/huggingface/hub/
"""

import numpy as np
from faster_whisper import WhisperModel


def load_model(model_size: str = "medium", device: str = "cpu") -> WhisperModel:
    """
    Whisper 모델을 로드합니다.

    Args:
        model_size: "small" / "medium" / "large-v3" 또는 로컬 경로 (예: "models/whisper-small-ko-zeroth")
        device: "cpu" 또는 "cuda"
    """
    compute_type = "float16" if device == "cuda" else "int8"

    print(f"[STT] 모델 로딩: {model_size} / {device} / {compute_type}")
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
    segments, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=5,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    # segments는 generator → 순회해야 결과가 나옴
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
    segments, _ = model.transcribe(
        audio.astype(np.float32),
        language=language,
        beam_size=2,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=300),
    )

    text = " ".join(segment.text.strip() for segment in segments)
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
