from contextvars import ContextVar

# 현재 세션 ID를 저장하는 컨텍스트 변수
# chat() 호출 시 설정되고, tool 함수에서 읽어감
current_session_id: ContextVar[str] = ContextVar("session_id", default="default")
