#/api/main.py

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.routes.menu import router as menu_router
from api.routes.stt import get_model, router as stt_router
from app.rag.chroma import get_chroma_db
from api.routes.cart import router as cart_router
from api.routes.order import router as order_router
from api.routes.search import router as search_router
from api.routes.options import router as options_router
from api.routes.sets import router as sets_router


# 욕설/비속어 키워드 목록
BLOCKED_KEYWORDS = [
    "씨발", "시발", "ㅅㅂ", "개새끼", "병신", "ㅂㅅ", "바보",
    "지랄", "ㅈㄹ", "미친", "ㅁㅊ", "새끼", "ㅅㄲ",
    "꺼져", "닥쳐", "죽어", "년", "놈", "빌어먹", "거지같", "존나", "ㅈㄴ",
    "좆", "보지", "니애미", "니엄마", "느금마",
    "찐따", "멍청", "바보", "돌아이",
    "꺼지", "죽을", "때려", "죽여",
    "fuck", "shit", "bitch","damn", "crap", "idiot", "stupid", "dumb",
    "wtf", "stfu", "asshole", "bastard"
]

def contains_blocked_keyword(text: str) -> bool:
    lowered = text.lower().replace(" ", "")
    return any(kw.replace(" ", "") in lowered for kw in BLOCKED_KEYWORDS)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    get_model()      # 서버 시작 시 Whisper 모델 미리 로드
    get_chroma_db()  # 서버 시작 시 ChromaDB 임베딩 모델 미리 로드
    yield


app = FastAPI(title="Sadollar AI API", lifespan=lifespan)

# 1차 필터링 미들웨어
@app.middleware("http")
async def filter_middleware(request: Request, call_next):
    if request.method == "POST":
        try:
            body = await request.json()
            text = body.get("text") or body.get("query") or body.get("message") or ""
            if contains_blocked_keyword(text):
                return JSONResponse(
                    status_code=400,
                    content={"message": "부적절한 표현이 포함되어 있습니다."}
                )
        except:
            pass

    response = await call_next(request)
    return response

# 헬스체크
@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}

app.include_router(menu_router)
app.include_router(cart_router)
app.include_router(order_router)
app.include_router(search_router)
app.include_router(stt_router)
app.include_router(options_router)
app.include_router(sets_router)