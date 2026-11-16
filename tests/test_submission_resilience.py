import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_submission import build

CODE='''import asyncio,json,os,httpx,solution
count=0
async def generate(value,**kwargs):
 global count
 data,_=json.JSONDecoder().raw_decode(value)
 if 'sources' not in data:return json.dumps({'queries':[],'documents':[]})
 count+=1
 scenario=os.environ['SCENARIO']
 if scenario=='unauthorized':
  response=httpx.Response(401,request=httpx.Request('POST','http://test.invalid'))
  response.raise_for_status()
 if scenario=='always_bad' or (scenario=='bad_then_good' and count<=2):return 'invalid JSON'
 if scenario=='quotes_then_good' and count<=2:
  return json.dumps({'status':'answer','answer':'Подтверждённый факт [S1]','evidence':[{'id':'S1','quote':'Выдуманная цитата, которой нет в источнике.'}]})
 source=data['sources'][0]
 return json.dumps({'status':'answer','answer':'Подтверждённый факт ['+source['id']+']','evidence':[]})
solution.generate_remote=generate
asyncio.run(solution.main())
print(json.dumps({'generation_calls':count}))
'''


def run_case(scenario,baseline=False):
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        archive=root/'submit.zip'
        if baseline:
            # Исходный solution сохранён в основном backend и совпадал с V8.
            build(archive,engine_path=ROOT/'experiments/stable/psb_engine.py')
        else:
            build(archive,engine_path=ROOT/'experiments/stable/psb_engine.py',solution_path=ROOT/'experiments/stable/solution.py')
        with ZipFile(archive) as z:z.extractall(root/'run')
        data=root/'data';data.mkdir()
        with ZipFile(data/'knowledge_base.zip','w') as z:
            z.writestr('Правило.txt','Правило: документ подтверждает проверяемый факт.')
        with (data/'questions.csv').open('w',encoding='utf-8',newline='') as f:
            writer=csv.writer(f);writer.writerow(['id','question']);writer.writerow(['case','Правило: секретный_тестовый_запрос'])
        report=root/'diagnostics.json'
        process=subprocess.run([sys.executable,'-c',CODE],cwd=root/'run',env={**os.environ,
            'DATA_DIR':str(data),'SCENARIO':scenario,'RAG_SEMANTIC':'0','PSB_DIAGNOSTICS_PATH':str(report)},
            capture_output=True,text=True,encoding='utf-8',timeout=15)
        if process.returncode:raise AssertionError(process.stderr)
        with (root/'run/submission.csv').open(encoding='utf-8') as stream:
            answer=list(csv.DictReader(stream))[0]['answer']
        diagnostic=json.loads(report.read_text(encoding='utf-8')) if report.exists() else None
        return {'exit_code':process.returncode,'fallback':'Упрощённый режим' in answer,
                'calls':json.loads(process.stdout.strip())['generation_calls'],'diagnostics':diagnostic}


class SubmissionResilienceTests(unittest.TestCase):
    def test_v8_success_can_hide_fallback(self):
        old=run_case('bad_then_good',baseline=True)
        new=run_case('bad_then_good')
        self.assertEqual(old['exit_code'],0)
        self.assertTrue(old['fallback'])
        self.assertFalse(new['fallback'])
        self.assertEqual(new['diagnostics']['recoveries'],1)

    def test_invalid_quote_recovers_without_relaxing_quote_validation(self):
        result=run_case('quotes_then_good')
        self.assertFalse(result['fallback'])
        self.assertEqual(result['calls'],3)

    def test_permanent_failure_is_bounded_and_visible(self):
        result=run_case('always_bad')
        self.assertTrue(result['fallback'])
        self.assertEqual(result['calls'],4)
        self.assertEqual(result['diagnostics']['fallbacks'],1)

    def test_success_has_no_extra_generation(self):
        result=run_case('good')
        self.assertEqual(result['calls'],1)
        self.assertFalse(result['fallback'])
        self.assertEqual(result['diagnostics']['recoveries'],0)
        self.assertNotIn('секретный_тестовый_запрос',json.dumps(result['diagnostics'],ensure_ascii=False))

    def test_unauthorized_does_not_restart_pipeline(self):
        result=run_case('unauthorized')
        self.assertEqual(result['calls'],1)
        self.assertTrue(result['fallback'])
