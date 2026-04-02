from fastapi import FastAPI
from api.routes.menu import router as menu_router

app = FastAPI(title="Sadollar AI API")

app.include_router(menu_router)