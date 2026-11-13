"""Точка входа сабмита ПСБ. Вход: DATA_DIR, выход: submission.csv."""
import asyncio
import csv
import io
import os
import sys
import time
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from psb_engine import KnowledgeBase, answer_question, generate_remote, PLANNER_SYSTEM


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
    async def answer(row):
        async with semaphore:
            started = time.monotonic()
            try:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError("Лимит времени сабмита")
                async def planner(value):
                    return await generate_remote(value,system=PLANNER_SYSTEM,max_tokens=1000)
                result = await asyncio.wait_for(answer_question(kb,row["question"],[],generate_remote,planner), timeout=min(180, remaining))
                text = result["answer"]
                for source in result["sources"]:
                    text = text.replace("["+source["id"]+"]", "["+source["title"]+", строки "+str(source["line_start"])+"–"+str(source["line_end"])+"]")
                print(f"ID {row['id']}: status={result['status']} sources={len(result['sources'])} seconds={time.monotonic()-started:.1f}", file=sys.stderr, flush=True)
                return row["id"], text[:10000]
            except Exception as exc:
                # Техническая ошибка не маскируется под отсутствие правовой нормы.
                print(f"ID {row['id']}: {type(exc).__name__} seconds={time.monotonic()-started:.1f}", file=sys.stderr, flush=True)
                return row["id"], "Техническая ошибка: не удалось сформировать проверяемый ответ."
    answers = await asyncio.gather(*(answer(row) for row in rows))
    with Path("submission.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_ALL)
        writer.writerow(["id", "answer"])
        writer.writerows(answers)


if __name__ == "__main__":
    asyncio.run(main())
