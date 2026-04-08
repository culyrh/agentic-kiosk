from fastapi import FastAPI

from api.routes.cart import router as cart_router
from api.routes.menu import router as menu_router
from api.routes.order import router as order_router
from api.routes.search import router as search_router
from api.routes.session import router as session_router

app = FastAPI(title="Sadollar AI API")

app.include_router(menu_router)
app.include_router(cart_router)
app.include_router(order_router)
app.include_router(search_router)
app.include_router(session_router)
