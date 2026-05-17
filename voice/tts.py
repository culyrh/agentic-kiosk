import asyncio
import io
import edge_tts

VOICE = "ko-KR-SunHiNeural"  # 한국어 여자 목소리
RATE = "+10%"                 # 말하는 속도 (+는 빠르게, -는 느리게)


async def synthesize_async(text: str) -> bytes:
    """텍스트를 MP3 오디오 바이트로 변환 (비동기)"""
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE)
    buf = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()


def synthesize(text: str) -> bytes:
    """텍스트를 MP3 오디오 바이트로 변환 (동기 래퍼)"""
    return asyncio.run(synthesize_async(text))
