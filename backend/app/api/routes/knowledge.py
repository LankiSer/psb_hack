from functools import lru_cache
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.psb_deps import get_current_user, get_ollama
from app.shared.ollama.client import OllamaClient
from psb_engine import KnowledgeBase, SYSTEM, SCHEMA, checked_answer, env, generate_remote

load_dotenv(Path(__file__).resolve().parents[3] / ".env", override=False)

router = APIRouter(prefix="/knowledge", tags=["knowledge"], dependencies=[Depends(get_current_user)])


@lru_cache
def knowledge() -> KnowledgeBase:
    return KnowledgeBase.from_path(Path(__file__).resolve().parents[3] / "psb_data" / "knowledge-base")


class Message(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    text: str = Field(max_length=10000)


class Question(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    history: list[Message] = Field(default_factory=list, max_length=10)


@router.get("/documents")
def documents():
    return [{k:v for k,v in d.items() if k != "text"} for d in knowledge().documents.values()]


@router.get("/documents/{document_id}")
def document(document_id: str):
    result = knowledge().documents.get(document_id)
    if not result:
        raise HTTPException(404, "Документ не найден")
    return result


@router.post("/ask")
async def ask(body: Question, ollama: OllamaClient = Depends(get_ollama)):
    history = [m.model_dump() for m in body.history]
    # Явная структура диалога позволяет поиску отличить последнее уточнение от старых реплик.
    query = "\n".join(("Пользователь: " if m.role == "user" else "Ассистент: ") + m.text for m in body.history[-6:]) + "\nПользователь: " + body.question
    fragments = knowledge().search(query)
    try:
        async def generate(user_prompt):
            return await generate_remote(user_prompt) if env("LLM_BASE_URL", "OPENAI_BASE_URL", "BASE_URL") else await ollama.chat(SYSTEM, user_prompt, max_tokens=5000, schema=SCHEMA, reasoning=True)
        return await checked_answer(body.question, history, fragments, generate, knowledge().catalog)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    except (httpx.HTTPError, RuntimeError, KeyError):
        raise HTTPException(503, "Модель недоступна. Повторите запрос позже.") from None
