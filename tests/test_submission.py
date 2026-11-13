"""Контракт архива и CSV. Использует тестовый транспорт, не реальную LLM."""
import csv
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_submission import build


class SubmissionContract(unittest.TestCase):
    def test_archive_runs_without_repository(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = build(root / "submit.zip")
            with ZipFile(archive) as z:
                self.assertEqual(set(z.namelist()), {"solution.py", "psb_engine.py", "requirements.txt"})
                z.extractall(root / "run")
            data = root / "data"
            data.mkdir()
            with ZipFile(data / "knowledge_base.zip", "w") as z:
                z.writestr("документы компании__Тест.txt", "Пункт 1. Документ подтверждает тестовый факт.")
            with (data / "questions.csv").open("w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["id", "question"])
                writer.writerow(["first", "Документ: первый независимый вопрос"])
                writer.writerow(["second", "Пользователь: Документ?\nАссистент: Уточните.\nПользователь: Тестовый факт?"])
            # Подменяем только генерацию: поиск, JSON-проверка, изоляция и CSV настоящие.
            code = '''import asyncio,json,solution
async def generate(value):
 data,_=json.JSONDecoder().raw_decode(value)
 assert all('первый независимый' not in m['text'] for m in data['history'])
 assert not ('первый независимый' in data['question'] and 'Уточните' in data['question'])
 source=data['sources'][0]
 return json.dumps({'status':'answer','answer':'Тестовый факт ['+source['id']+']','evidence':[{'id':source['id'],'quote':source['text']}]})
solution.generate_remote=generate
asyncio.run(solution.main())
'''
            result = subprocess.run([sys.executable, "-c", code], cwd=root / "run", env={**os.environ, "DATA_DIR": str(data)}, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            with (root / "run/submission.csv").open(encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                self.assertEqual(reader.fieldnames, ["id", "answer"])
                rows = list(reader)
            self.assertEqual([r["id"] for r in rows], ["first", "second"])
            self.assertTrue(all(0 < len(r["answer"]) <= 10000 for r in rows))


if __name__ == "__main__":
    unittest.main()
