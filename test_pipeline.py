"""
전체 파이프라인 테스트 스크립트

동작 흐름:
  마이크(sounddevice)
    → audio_callback (sounddevice 내부 스레드)
    → asyncio.Queue (스레드 경계 안전하게 전달)
    → send_audio() (WS로 50ms 청크 전송)
    → WS /stt/ws (서버 처리):
        1. VAD: RMS 에너지 기반 발화 구간 감지, 무음 0.8초 지속 시 발화 종료 판정
        2. STT: Whisper(faster-whisper small) 로 음성 → 텍스트 변환
        3. 정제: GPT-4o-mini로 STT 오인식(메뉴명 오류, 잡음성 발화 등) 교정
        4. 에이전트: GPT-4o 기반 LangChain ReAct 에이전트 실행
           - 사용 가능한 툴 8개:
               search_menu      : 자연어 메뉴 검색 (ChromaDB 벡터검색 or SQLite 페이지네이션)
               get_menu_by_price: 가격 기준 메뉴 조회
               get_menu_info    : 특정 메뉴 상세 정보 조회
               add_to_cart      : 장바구니 추가 (퍼지 매칭)
               remove_from_cart : 장바구니 항목 제거 (퍼지 매칭)
               view_cart        : 현재 장바구니 조회
               confirm_order    : 주문 확정 및 결제 처리
               clear_cart       : 장바구니 전체 비우기
           - 대화 히스토리를 session_id 단위로 메모리에 유지
    → receive() (서버 응답 수신 및 출력)
        - text frame: JSON (stt_text, refined_text, voice, screen)
        - binary frame: TTS MP3 오디오 (--play-audio 옵션 시 로컬 재생)

주요 구조:
  - sounddevice 콜백은 별도 스레드에서 실행되므로 직접 ws.send()를 호출하면 안 됨
    → call_soon_threadsafe + Queue로 이벤트 루프에 안전하게 넘김
  - send_audio / receive 를 각각 별도 task로 실행해서
    송신과 수신이 서로 블로킹하지 않고 동시에 동작
  - await asyncio.Future()로 메인 코루틴을 무한 대기시켜
    Ctrl+C 전까지 스트리밍 유지

사용:
  python test_pipeline.py                # 텍스트 출력만
  python test_pipeline.py --play-audio   # 텍스트 출력 + TTS 음성 재생 (백엔드 로컬 테스트용)
"""

import argparse
import asyncio
import io
import json
import threading

import numpy as np
import sounddevice as sd
import websockets

SAMPLE_RATE = 16000
CHUNK_SAMPLES = 800  # 16000Hz × 0.05s = 800 샘플 (50ms 단위, 서버 VAD와 동일)

# TTS 재생 중 마이크 입력 차단용 플래그 (스레드 안전)
_tts_playing = threading.Event()


def play_audio(audio_bytes: bytes):
    """MP3 바이트를 로컬 스피커로 재생 (백엔드 테스트 전용)"""
    import pygame
    pygame.mixer.init()
    pygame.mixer.music.load(io.BytesIO(audio_bytes))
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        pygame.time.wait(50)


async def main(session_id: str = "test", play_audio_flag: bool = False):
    uri = f"ws://localhost:8000/stt/ws?session_id={session_id}"
    print("서버 연결 중...")
    if play_audio_flag:
        print("[오디오 재생 모드] TTS 음성을 로컬에서 재생합니다.\n")

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    def audio_callback(indata, frames, time_info, status):
        # TTS 재생 중이면 마이크 입력을 버림 → 스피커 출력이 STT로 다시 들어가는 피드백 루프 방지
        if _tts_playing.is_set():
            return
        # sounddevice 내부 스레드에서 호출됨 → 이벤트 루프에 안전하게 전달
        chunk = indata[:, 0].astype(np.float32).tobytes()  # 스테레오면 첫 채널만 사용
        loop.call_soon_threadsafe(queue.put_nowait, chunk)

    async with websockets.connect(uri) as ws:
        print("마이크 대기 중... (Ctrl+C로 종료)\n")

        async def send_audio():
            # Queue에서 청크를 꺼내 서버로 전송
            # 서버는 50ms 청크 단위로 VAD를 수행하므로 끊김 없이 보내야 함
            while True:
                chunk = await queue.get()
                await ws.send(chunk)

        async def receive():
            # 서버 응답은 두 종류의 frame으로 옴:
            #   text frame  : JSON { stt_text, refined_text, voice, screen }
            #   binary frame: TTS MP3 오디오 바이트 (JSON 직후 전송됨)
            # stt_text   : Whisper 인식 원문
            # refined_text: LLM 정제 결과
            # voice      : 에이전트 응답 중 음성으로 읽을 내용
            # screen     : 에이전트 응답 중 화면에만 표시할 내용 ([SCREEN] 태그 파싱 결과)
            async for msg in ws:
                if isinstance(msg, bytes):
                    # binary frame = TTS 오디오
                    if play_audio_flag:
                        _tts_playing.set()
                        # 큐에 남아있는 직전 청크도 버림 (재생 시작 직전 잡음 제거)
                        while not queue.empty():
                            try:
                                queue.get_nowait()
                            except asyncio.QueueEmpty:
                                break
                        try:
                            await asyncio.to_thread(play_audio, msg)
                        finally:
                            # 음향 잔향이 마이크에 남을 수 있으므로 짧게 대기 후 해제
                            await asyncio.sleep(0.3)
                            _tts_playing.clear()
                else:
                    # text frame = JSON 응답
                    data = json.loads(msg)
                    print(f"[STT]  {data['stt_text']}")
                    print(f"[정제] {data.get('refined_text', '')}")
                    print(f"[음성] {data['voice']}")
                    screen = data.get('screen')
                    if screen:
                        if isinstance(screen, list):
                            for item in screen:
                                print(f"[화면] {item['name']} | {item['price']}원 | {item.get('img_url', '')}")
                        else:
                            print(f"[화면] {screen}")
                    if data.get('action'):
                        print(f"[액션] {data['action']}")
                    print()

        send_task = asyncio.create_task(send_audio())
        recv_task = asyncio.create_task(receive())

        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=CHUNK_SAMPLES,  # 50ms마다 audio_callback 호출
            callback=audio_callback,
        ):
            try:
                await asyncio.Future()  # Ctrl+C 전까지 무한 대기
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass
            finally:
                send_task.cancel()
                recv_task.cancel()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--play-audio", action="store_true", help="TTS 음성을 로컬 스피커로 재생 (백엔드 테스트용)")
    args = parser.parse_args()

    try:
        asyncio.run(main(play_audio_flag=args.play_audio))
    except KeyboardInterrupt:
        print("\n[종료]")
