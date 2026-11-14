from functools import lru_cache
from pathlib import Path

import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
import asyncio
import re
from pydantic import BaseModel, Field

from app.api.psb_deps import get_current_user, get_ollama, get_upload_service
from app.domains.knowledge.service import UploadService
from app.domains.auth.models import User
from app.shared.ollama.client import OllamaClient, IncompleteAnswerError
from psb_engine import KnowledgeBase, SYSTEM, SCHEMA, PLANNER_SYSTEM, PLAN_SCHEMA, answer_question, env, generate_remote, contract_ids

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
def documents(user: User=Depends(get_current_user), uploads: UploadService=Depends(get_upload_service)):
    kb=uploads.make_knowledge(Path(__file__).resolve().parents[3]/'psb_data/knowledge-base',user.id)
    own={r['document_id']:r for r in uploads.list(user.id) if r['status']=='ready'}
    return [{**{k:v for k,v in d.items() if k!='text'},'uploaded':d['id'] in own,
             'upload_id':own[d['id']]['id'] if d['id'] in own else None} for d in kb.documents.values()]


@router.get("/documents/{document_id}")
def document(document_id: str,user: User=Depends(get_current_user), uploads: UploadService=Depends(get_upload_service)):
    result = uploads.make_knowledge(Path(__file__).resolve().parents[3]/'psb_data/knowledge-base',user.id).documents.get(document_id)
    if not result:
        raise HTTPException(404, "Документ не найден")
    return result


@router.post("/ask")
async def ask(body: Question, ollama: OllamaClient = Depends(get_ollama),user: User=Depends(get_current_user),uploads: UploadService=Depends(get_upload_service)):
    history = [m.model_dump() for m in body.history]
    try:
        kb=await asyncio.to_thread(uploads.make_knowledge,Path(__file__).resolve().parents[3]/'psb_data/knowledge-base',user.id)
        retrieval_hints,warning=await uploads.hints(user.id,body.question)
        remote = bool(env("LLM_BASE_URL", "OPENAI_BASE_URL", "BASE_URL"))
        async def generate(user_prompt):
            # Быстрый локальный чат: бюджет целиком на ответ, а не скрытое рассуждение.
            return await generate_remote(user_prompt) if remote else await ollama.chat(SYSTEM, user_prompt, max_tokens=1600, schema=SCHEMA, reasoning=False, num_ctx=16384)
        async def planner(value):
            return await generate_remote(value,system=PLANNER_SYSTEM,max_tokens=1000) if remote else await ollama.chat(PLANNER_SYSTEM,value,max_tokens=350,schema=PLAN_SCHEMA,reasoning=False,num_ctx=16384)
        # Для явно указанного договора обычный поиск уже выбирает его и допсоглашения.
        focused = bool(contract_ids(body.question)) and not re.search(r'стать|закон|кодекс|\b(?:ТК|НК|ГК|КоАП)\b',body.question,re.I)
        plan = planner if remote or not focused else None
        result=await asyncio.wait_for(answer_question(kb,body.question,history,generate,plan,retrieval_hints,
            search_limit=2 if focused and not remote else 8),timeout=150 if remote else 75)
        if warning: result['retrieval_warning']=warning
        return result
    except ValueError:
        raise HTTPException(503, "Не удалось проверить ответ модели. Попробуйте уточнить вопрос и повторить запрос.") from None
    except TimeoutError:
        raise HTTPException(504, "Модель отвечает дольше обычного. Попробуйте задать более короткий вопрос.") from None
    except IncompleteAnswerError:
        raise HTTPException(503, "Модель не завершила ответ. Попробуйте задать вопрос короче или повторить запрос.") from None
    except (httpx.HTTPError, RuntimeError, KeyError):
        raise HTTPException(503, "Модель недоступна. Повторите запрос позже.") from None


@router.get('/uploads')
def upload_list(user: User=Depends(get_current_user),uploads: UploadService=Depends(get_upload_service)):
    return uploads.list(user.id)


@router.post('/uploads',status_code=202)
async def upload(file: UploadFile=File(...),user: User=Depends(get_current_user),uploads: UploadService=Depends(get_upload_service)):
    try:
        raw=bytearray()
        while chunk:=await file.read(1024*1024):
            raw.extend(chunk)
            if len(raw)>uploads.settings.max_upload_bytes: raise HTTPException(413,'Максимальный размер файла — 25 МБ.')
        return await asyncio.to_thread(uploads.add,user.id,file.filename or 'document',bytes(raw))
    except ValueError as exc: raise HTTPException(422,str(exc)) from None
    finally: await file.close()


@router.post('/uploads/{upload_id}/retry')
def retry_upload(upload_id: str,user: User=Depends(get_current_user),uploads: UploadService=Depends(get_upload_service)):
    try: return uploads.retry(user.id,upload_id)
    except LookupError: raise HTTPException(404,'Документ не найден.') from None
    except ValueError as exc: raise HTTPException(409,str(exc)) from None


@router.delete('/uploads/{upload_id}',status_code=204)
async def delete_upload(upload_id: str,user: User=Depends(get_current_user),uploads: UploadService=Depends(get_upload_service)):
    try: await uploads.delete(user.id,upload_id)
    except LookupError: raise HTTPException(404,'Документ не найден.') from None


@router.get('/uploads/{upload_id}/download')
def download_upload(upload_id: str,user: User=Depends(get_current_user),uploads: UploadService=Depends(get_upload_service)):
    with uploads.sessions() as db:
        try: row=uploads.owned(db,user.id,upload_id)
        except LookupError: raise HTTPException(404,'Документ не найден.') from None
        return FileResponse(uploads.path(row.id),filename=row.filename,media_type='application/octet-stream')
