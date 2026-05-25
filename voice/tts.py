import asyncio
import io
import wave

import numpy as np

_VOICE_NAME = "F1"
_LANG = "ko"

_tts = None
_style = None


def _get_tts():
    global _tts, _style
    if _tts is None:
        from supertonic import TTS
        _tts = TTS(model="supertonic-3")
        _style = _tts.get_voice_style(_VOICE_NAME)
    return _tts, _style


def synthesize(text: str) -> bytes:
    tts, style = _get_tts()
    wav_arr, _ = tts.synthesize(text, style, lang=_LANG)
    # wav_arr: float32 ndarray shape (1, N) in range [-1, 1]
    samples = wav_arr[0]
    pcm = np.clip(samples, -1.0, 1.0)
    pcm_int16 = (pcm * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(tts.sample_rate)
        wf.writeframes(pcm_int16.tobytes())
    buf.seek(0)
    return buf.read()


async def synthesize_async(text: str) -> bytes:
    return await asyncio.to_thread(synthesize, text)
