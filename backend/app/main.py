from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import auth, knowledge
from app.shared.db import init_db

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    yield

app = FastAPI(title="ПСБ Банк Docs", description="Юридический ассистент по предоставленной базе знаний", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"], allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])
app.include_router(auth.router, prefix="/api")
app.include_router(knowledge.router, prefix="/api")

@app.get("/api/health")
def health():
    return {"status": "ok", "documents": len(knowledge.knowledge().documents), "mode": "psb"}

@app.get("/")
def root():
    return {"service": "psb-bank-docs", "docs": "/docs", "health": "/api/health"}
