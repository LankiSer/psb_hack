from contextlib import asynccontextmanager
from contextlib import suppress
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import auth, knowledge
from app.shared.db import init_db
from app.api.psb_deps import get_upload_service
from app.config import get_settings

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    worker=asyncio.create_task(get_upload_service().run())
    try: yield
    finally:
        worker.cancel()
        with suppress(asyncio.CancelledError): await worker

app = FastAPI(title="ПСБ Банк Docs", description="Юридический ассистент по предоставленной базе знаний", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=get_settings().cors_origins.split(','), allow_methods=["GET", "POST", "DELETE"], allow_headers=["Authorization", "Content-Type"])
app.include_router(auth.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")

@app.get("/api/health")
def health():
    return {"status": "ok", "documents": len(knowledge.knowledge().documents), "mode": "psb"}

@app.get("/")
def root():
    return {"service": "psb-bank-docs", "docs": "/docs", "health": "/api/health"}
