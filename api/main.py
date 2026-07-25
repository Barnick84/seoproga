import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api.routers import (
    admin,
    analysis,
    billing,
    cluster,
    health,
    keywords,
    positions,
    sites,
    users,
    wordstat,
)


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, ensure_ascii=False)


_handler = logging.StreamHandler()
_handler.setFormatter(JSONFormatter())
_root = logging.getLogger()
_root.handlers.clear()
_root.addHandler(_handler)
_root.setLevel(logging.INFO)

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="SEO Auto Cluster API",
    description="Python FastAPI backend for SEO automation and clustering",
    version="1.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
origins_raw = os.getenv("CORS_ORIGINS", "")
if not origins_raw:
    raise RuntimeError(
        "CORS_ORIGINS must be set in .env (e.g. CORS_ORIGINS=http://localhost:3000,https://example.com)"
    )
origins = [o.strip() for o in origins_raw.split(",") if o.strip()]
if "*" in origins and len(origins) > 1:
    raise RuntimeError("CORS_ORIGINS cannot mix '*' with specific origins")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=("*" not in origins),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def structured_logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())[:8]
    request.state.request_id = request_id
    start_time = time.time()

    response = await call_next(request)

    process_time = time.time() - start_time
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{process_time:.4f}"

    extra = logging.LogRecord(
        name=__name__,
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    )
    extra.request_id = request_id
    logger.info(
        f"{request.method} {request.url.path} {response.status_code} {process_time:.4f}s",
        extra={"request_id": request_id},
    )
    return response


# Include routers
app.include_router(health.router)
app.include_router(users.router)
app.include_router(sites.router)
app.include_router(keywords.router)
app.include_router(analysis.router)
app.include_router(billing.router)
app.include_router(admin.router)
app.include_router(cluster.router)
app.include_router(wordstat.router)
app.include_router(positions.router)

# Mount public static files if the directory exists
public_dir = os.path.join(os.path.dirname(__file__), "public")
if os.path.exists(public_dir):
    app.mount("/", StaticFiles(directory=public_dir, html=True), name="public")
