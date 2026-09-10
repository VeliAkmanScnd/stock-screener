from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.api.admin_routes import router as admin_router
from app.api.auth_deps import optional_user
from app.api.auth_routes import router as auth_router
from app.api.schedule_routes import router as schedule_router
from app.api.track_routes import router as track_router
from app.api.routes import router
from app.config import BASE_DIR
from app.database import get_db
from app.services.scheduler import start_scheduler, stop_scheduler
from app.services.twelvedata_client import TwelveDataError


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="TradeLABtr Stock Screener", version="1.0.0", lifespan=lifespan)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(schedule_router)
app.include_router(track_router)
app.include_router(router)


@app.exception_handler(TwelveDataError)
async def twelve_data_error_handler(_request: Request, exc: TwelveDataError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled_error_handler(_request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": f"Sunucu hatası: {exc}"},
    )

static_dir = BASE_DIR / "static"
templates_dir = BASE_DIR / "templates"

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html")


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    db: Session = Depends(get_db),
    user=Depends(optional_user),
):
    if user is None:
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(request, "index.html")
