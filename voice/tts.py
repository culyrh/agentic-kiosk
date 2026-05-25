import asyncio
import io

import soundfile as sf

_model = None
_speaker_id = None
_sample_rate = None


def _get_model():
    global _model, _speaker_id, _sample_rate
    if _model is None:
        from melo.api import TTS
        _model = TTS(language="KR", device="cpu")
        _speaker_id = _model.hps.data.spk2id["KR"]
        _sample_rate = _model.hps.data.sampling_rate
    return _model, _speaker_id, _sample_rate


def synthesize(text: str) -> bytes:
    model, speaker_id, sample_rate = _get_model()
    audio = model.tts_to_file(text, speaker_id, output_path=None, speed=1.3, noise_scale=0.3, quiet=True)
    buf = io.BytesIO()
    sf.write(buf, audio, sample_rate, format="WAV")
    buf.seek(0)
    return buf.read()


async def synthesize_async(text: str) -> bytes:
    return await asyncio.to_thread(synthesize, text)
