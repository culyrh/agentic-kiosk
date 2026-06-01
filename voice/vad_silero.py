"""Silero VAD streaming wrapper.

StreamingVAD.feed() accepts arbitrary-size float32 PCM chunks at 16kHz
and returns a complete utterance array when speech ends, else None.
"""

from collections import deque

import numpy as np
import torch
from silero_vad import VADIterator, load_silero_vad

SAMPLE_RATE = 16000
CHUNK_SIZE = 512       # Silero VAD requires exactly 512 samples at 16kHz (32ms)
PRE_ROLL_CHUNKS = 4    # 4 × 32ms = 128ms pre-roll captured before start detection
MIN_SILENCE_MS = 500   # 800 → 500ms: 키오스크 단문 명령에 최적화
SPEECH_PAD_MS = 50     # 100 → 50ms
THRESHOLD = 0.65       # 0.5 → 0.65: 확신도 높은 발화만 통과 (원거리 대화 필터)

# 세션 시작 시 자동 보정 전 기본 게이트 (보정 완료 전 잠깐 사용)
ENERGY_GATE = 0.02

# 마이크 AGC 안정화 대기 시간 (이 구간은 버림)
CALIBRATION_WARMUP_SEC = 0.5
# 워밍업 이후 실제 소음 측정 시간
CALIBRATION_SEC = 1.5
# 측정된 소음 RMS에 곱하는 배수
CALIBRATION_MULTIPLIER = 1.5

_model = None


def _get_model():
    global _model
    if _model is None:
        _model = load_silero_vad()
    return _model


class StreamingVAD:
    """Stateful per-connection Silero VAD.

    Feed audio chunks of any size; returns utterance audio when speech ends.
    """

    def __init__(
        self,
        threshold: float = THRESHOLD,
        min_silence_ms: int = MIN_SILENCE_MS,
        speech_pad_ms: int = SPEECH_PAD_MS,
        energy_gate: float = ENERGY_GATE,
        calibration_sec: float = CALIBRATION_SEC,
        calibration_multiplier: float = CALIBRATION_MULTIPLIER,
    ):
        self._vad = VADIterator(
            _get_model(),
            threshold=threshold,
            sampling_rate=SAMPLE_RATE,
            min_silence_duration_ms=min_silence_ms,
            speech_pad_ms=speech_pad_ms,
        )
        self._energy_gate = energy_gate
        self._buf = np.zeros(0, dtype=np.float32)
        self._speech: list[np.ndarray] = []
        self._pre_roll: deque[np.ndarray] = deque(maxlen=PRE_ROLL_CHUNKS)
        self._in_speech = False

        # 캘리브레이션 상태
        self._calibrated = False
        self._calib_warmup_samples = int(SAMPLE_RATE * CALIBRATION_WARMUP_SEC)
        self._calib_samples_needed = int(SAMPLE_RATE * calibration_sec)
        self._calib_multiplier = calibration_multiplier
        self._calib_collected = 0   # 지금까지 처리한 샘플 수
        self._calib_buf: list[float] = []   # 워밍업 이후 구간 RMS 값들

    @property
    def in_speech(self) -> bool:
        return self._in_speech

    def feed(self, chunk: np.ndarray) -> np.ndarray | None:
        """Feed a float32 PCM chunk. Returns utterance array when speech ends."""
        self._buf = np.concatenate([self._buf, chunk])
        completed = None

        while len(self._buf) >= CHUNK_SIZE:
            window = self._buf[:CHUNK_SIZE].copy()
            self._buf = self._buf[CHUNK_SIZE:]

            # ── 캘리브레이션 단계 ────────────────────────────────────────
            if not self._calibrated:
                self._calib_collected += CHUNK_SIZE

                # 워밍업 구간(0.5초)은 버림 — 마이크 AGC 안정화 대기
                if self._calib_collected > self._calib_warmup_samples:
                    rms = float(np.sqrt(np.mean(window ** 2)))
                    self._calib_buf.append(rms)

                    measured = len(self._calib_buf) * CHUNK_SIZE
                    if measured >= self._calib_samples_needed:
                        # p75: 순간 튀는 값 제거, 전형적인 소음 수준 반영
                        noise_rms = float(np.percentile(self._calib_buf, 75))
                        self._energy_gate = noise_rms * self._calib_multiplier
                        self._calibrated = True
                        print(
                            f"[VAD] 캘리브레이션 완료 "
                            f"(워밍업 {CALIBRATION_WARMUP_SEC}s 제외): "
                            f"소음 p75={noise_rms:.4f} → "
                            f"gate={self._energy_gate:.4f}"
                        )
                continue   # 캘리브레이션 중엔 발화 감지 스킵
            # ────────────────────────────────────────────────────────────

            result = self._vad(torch.from_numpy(window), return_seconds=False)

            if not self._in_speech:
                self._pre_roll.append(window)
                rms = float(np.sqrt(np.mean(window ** 2)))
                if result and "start" in result:
                    if rms >= self._energy_gate:
                        print(f"[VAD] start ✓  rms={rms:.4f} (gate={self._energy_gate:.4f})")
                        self._in_speech = True
                        self._speech = list(self._pre_roll)
                    else:
                        print(f"[VAD] blocked rms={rms:.4f} (gate={self._energy_gate:.4f})")
            else:
                self._speech.append(window)
                if result and "end" in result:
                    completed = np.concatenate(self._speech)
                    self._speech = []
                    self._pre_roll.clear()
                    self._in_speech = False
                    self._vad.reset_states()

        return completed

    def flush(self) -> np.ndarray | None:
        """파일 끝 등 강제 종료 시 미완성 발화 반환. 실시간 스트림에서는 쓰지 않음."""
        if self._in_speech and self._speech:
            result = np.concatenate(self._speech)
            self.reset()
            return result
        return None

    def reset(self):
        self._buf = np.zeros(0, dtype=np.float32)
        self._speech.clear()
        self._pre_roll.clear()
        self._in_speech = False
        self._vad.reset_states()
