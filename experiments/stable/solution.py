"""Точка входа сабмита ПСБ. Вход: DATA_DIR, выход: submission.csv."""
import asyncio
import csv
import io
import json
import httpx
import os
import sys
import time
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from psb_engine import KnowledgeBase, answer_question, generate_remote, PLANNER_SYSTEM, lexical_deadline_answer
from psb_retrieval import RemoteRetrieval

# Пороги остатка общего дедлайна 1100 с: урезаем пайплайн, а не гадаем да/нет.
FAST_REMAINING = 70
DEADLINE_REMAINING = 12


def load_documents(path):
    documents = []
    with ZipFile(path) as archive:
        for name in archive.namelist():
            if name.startswith("__MACOSX/") or Path(name).suffix.lower() not in {".txt", ".md", ".docx"}:
                continue
            raw = archive.read(name)
            if name.lower().endswith(".docx"):
                with ZipFile(io.BytesIO(raw)) as doc:
                    root = ElementTree.fromstring(doc.read("word/document.xml"))
                ns = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
                text = "\n".join("".join(t.text or "" for t in p.iter(ns+"t")) for p in root.iter(ns+"p"))
            else:
                text = raw.decode("utf-8-sig")
            documents.append((name, text))
    return documents


def format_answer(result):
    text = result["answer"]
    for source in result.get("sources", []):
        text = text.replace("["+source["id"]+"]", "["+source["title"]+", строки "+str(source["line_start"])+"–"+str(source["line_end"])+"]")
    return text[:10000]


def pick_mode(remaining: float) -> str:
    if remaining <= DEADLINE_REMAINING:
        return "deadline"
    if remaining <= FAST_REMAINING:
        return "fast"
    return "full"


async def main():
    root = Path(os.environ.get("DATA_DIR", "data"))
    archive = next((root/n for n in ("knowledge-base.zip", "knowledge_base.zip", "kb.zip") if (root/n).is_file()), None)
    if not archive:
        raise FileNotFoundError("Не найден архив базы знаний")
    kb = KnowledgeBase(load_documents(archive))
    with (root/"questions.csv").open(encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows or any(not row.get("id") or not row.get("question") for row in rows) or len({row["id"] for row in rows}) != len(rows):
        raise ValueError("Нужны уникальные id и непустые question")
    semaphore = asyncio.Semaphore(max(1,min(8,int(os.environ.get("MAX_WORKERS", "4")))))
    # Оставляем время на запись CSV до лимита платформы в 20 минут.
    deadline = asyncio.get_running_loop().time() + 1100
    retrieval = RemoteRetrieval(kb)
    ready = await retrieval.prepare()
    print(f"Semantic retrieval: {'ready' if ready else 'lexical fallback'}",file=sys.stderr,flush=True)

    traces = []

    async def run_mode(row, mode, budget, trace):
        if mode == "deadline":
            return lexical_deadline_answer(kb, row["question"])
        async def measured_generate(value, **kwargs):
            event={'stage':'planner' if kwargs.get('system')==PLANNER_SYSTEM else 'answer'}
            trace['calls'].append(event)
            started=time.monotonic()
            try:
                result=await generate_remote(value,**kwargs)
                event['status']='ok'
                event['response_chars']=len(result)
                return result
            except BaseException as exc:
                event['status']=type(exc).__name__
                if isinstance(exc,httpx.HTTPStatusError):event['http_status']=exc.response.status_code
                raise
            finally:event['seconds']=round(time.monotonic()-started,3)
        async def planner(value):
            return await measured_generate(value, system=PLANNER_SYSTEM, max_tokens=1000)
        async def process():
            hints = {}
            if mode == "full" and ready:
                hints = await retrieval.hints(row["question"])
            return await answer_question(
                kb, row["question"], [], measured_generate,
                planner if mode == "full" else None,
                retrieval_hints=hints,
                allow_plan=(mode == "full"),
                allow_review=(mode == "full"),
            )
        return await asyncio.wait_for(process(), timeout=budget)

    async def answer(row):
        async with semaphore:
            started = time.monotonic()
            trace={'id':row['id'],'calls':[],'recovery_attempted':False,'fallback':False}
            traces.append(trace)
            try:
                remaining = deadline - asyncio.get_running_loop().time()
                mode = pick_mode(remaining)
                if remaining <= 0:
                    result = lexical_deadline_answer(kb, row['question'])
                    trace.update(mode='deadline',status=result['status'],fallback=True)
                    return row['id'],format_answer(result)
                # Полный режим до 180 с; быстрый — короче, чтобы хватило соседям по очереди.
                budget = min(180 if mode == "full" else 55, max(3.0, remaining - 1.0))
                try:
                    result = await run_mode(row, mode, budget, trace)
                except (TimeoutError,ValueError,RuntimeError,httpx.HTTPError) as error:
                    trace['recovery_reason']=type(error).__name__
                    # Повтор не исправит отсутствие авторизации или неизвестный endpoint.
                    if isinstance(error,httpx.HTTPStatusError) and error.response.status_code in {401,403,404}:
                        raise
                    leftover = deadline - asyncio.get_running_loop().time()
                    # Один запасной проход легче полного; без рандомных да/нет.
                    if leftover >= 20:
                        mode = "fast"
                        trace["recovery_attempted"]=True
                        result = await run_mode(row, mode, min(45.0, leftover - 1.0), trace)
                    elif leftover >= 1:
                        mode = "deadline"
                        result = lexical_deadline_answer(kb, row["question"])
                    else:
                        raise
                print(f"ID {row['id']}: mode={mode} status={result['status']} sources={len(result['sources'])} seconds={time.monotonic()-started:.1f}", file=sys.stderr, flush=True)
                trace.update(mode=mode,status=result["status"],fallback=(mode=="deadline"))
                return row["id"], format_answer(result)
            except Exception as exc:
                trace["error"]=type(exc).__name__
                # Техническая ошибка не маскируется под отсутствие правовой нормы.
                leftover = deadline - asyncio.get_running_loop().time()
                if leftover >= 0:
                    result = lexical_deadline_answer(kb, row["question"])
                    print(f"ID {row['id']}: {type(exc).__name__}->deadline status={result['status']} seconds={time.monotonic()-started:.1f}", file=sys.stderr, flush=True)
                    trace.update(mode=mode,status=result["status"],fallback=True)
                    return row["id"], format_answer(result)
                print(f"ID {row['id']}: {type(exc).__name__} seconds={time.monotonic()-started:.1f}", file=sys.stderr, flush=True)
                trace.update(mode='error',status='error',fallback=True)
                return row["id"], "Техническая ошибка: не удалось сформировать проверяемый ответ."
            finally:
                trace['seconds']=round(time.monotonic()-started,3)
    answers = await asyncio.gather(*(answer(row) for row in rows))
    with Path("submission.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(["id", "answer"])
        writer.writerows(answers)
    # Диагностика локального запуска: без вопросов, документов, ответов, URL и секретов.
    if os.environ.get('PSB_DIAGNOSTICS_PATH'):
        try:
            Path(os.environ['PSB_DIAGNOSTICS_PATH']).write_text(json.dumps({
                'semantic_ready':ready,'questions':len(rows),'fallbacks':sum(t['fallback'] for t in traces),
                'recoveries':sum(t['recovery_attempted'] and not t['fallback'] for t in traces),
                'rows':traces},ensure_ascii=False,indent=2),encoding='utf-8')
        except OSError:
            print('Local diagnostics could not be written',file=sys.stderr)


if __name__ == "__main__":
    asyncio.run(main())
