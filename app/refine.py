from dotenv import load_dotenv
load_dotenv()

from langchain_openai import ChatOpenAI

_llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

REFINE_PROMPT = """당신은 음성 인식(STT) 결과를 교정하는 도우미입니다.
패스트푸드 키오스크에서 고객이 말한 내용을 Whisper가 텍스트로 변환한 결과를 받습니다.

교정 규칙:
- 오인식된 메뉴명, 한국어 발음 오류를 수정하라. (예: "불고기 버그" → "불고기버거")
- 잡음, 의미 없는 감탄사("어", "음", "그", "저기"), 반복 제거
- 구어체는 유지하되 명확한 오기만 수정
- 의도나 의미는 절대 바꾸지 말 것
- 교정된 텍스트만 출력하고 설명은 쓰지 말 것

입력이 이미 명확하면 그대로 출력하라."""


def refine_stt(text: str) -> str:
    messages = [
        {"role": "system", "content": REFINE_PROMPT},
        {"role": "user", "content": text},
    ]
    result = _llm.invoke(messages)
    return result.content.strip()
