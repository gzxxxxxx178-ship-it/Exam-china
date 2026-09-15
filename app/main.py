from fastapi import FastAPI

from app.api.routes import router
from app.config import get_settings


app = FastAPI(title=get_settings().app_name, version="0.1.0")
app.include_router(router)
