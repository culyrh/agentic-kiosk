from contextlib import asynccontextmanager

from fastapi import FastAPI

from api.routes.menu import router as menu_router
from api.routes.stt import get_model, router as stt_router


@asynccontextmanager
async def lifespan(_app: FastAPI):
    get_model()  # 서버 시작 시 Whisper 모델 미리 로드
    yield


app = FastAPI(title="Sadollar AI API", lifespan=lifespan)

app.include_router(menu_router)
app.include_router(stt_router)
