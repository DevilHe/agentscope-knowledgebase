import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin_audit, admin_documents, chat, health, org, sessions
from app.auth.router import router as auth_router
from app.config import settings
from app.db.models import SessionLocal, init_db
from app.db.seed import seed_users
from app.services.knowledge_base import ensure_collection


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.resolved_upload_dir).mkdir(parents=True, exist_ok=True)
    for _ in range(30):
        try:
            init_db()
            db = SessionLocal()
            try:
                seed_users(db)
            finally:
                db.close()
            await ensure_collection()
            break
        except Exception:
            time.sleep(2)
    yield


app = FastAPI(title="AgentScope Knowledge Base", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(chat.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(admin_documents.router, prefix="/api")
app.include_router(admin_audit.router, prefix="/api")
app.include_router(org.router, prefix="/api")
