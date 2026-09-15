from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.config import PROJECT_ROOT, get_settings


app = FastAPI(title=get_settings().app_name, version="0.3.0")
app.include_router(router)
app.mount(
    "/static", StaticFiles(directory=PROJECT_ROOT / "app" / "static"), name="static"
)


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(PROJECT_ROOT / "app" / "static" / "index.html")
