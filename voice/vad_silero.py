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
MIN_SILENCE_MS = 800
SPEECH_PAD_MS = 100
THRESHOLD = 0.5

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
    ):
        self._vad = VADIterator(
            _get_model(),
            threshold=threshold,
            sampling_rate=SAMPLE_RATE,
            min_silence_duration_ms=min_silence_ms,
            speech_pad_ms=speech_pad_ms,
        )
        self._buf = np.zeros(0, dtype=np.float32)
        self._speech: list[np.ndarray] = []
        self._pre_roll: deque[np.ndarray] = deque(maxlen=PRE_ROLL_CHUNKS)
        self._in_speech = False

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

            result = self._vad(torch.from_numpy(window), return_seconds=False)

            if not self._in_speech:
                self._pre_roll.append(window)
                if result and "start" in result:
                    self._in_speech = True
                    self._speech = list(self._pre_roll)
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
