"""Полный путь CSV -> solution -> CSV на локальной Ollama, с диагностикой кандидата."""
import argparse
import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]
CODE='''import asyncio,httpx,solution,psb_engine
async def generate(value,**kwargs):
 planner=kwargs.get('system')==psb_engine.PLANNER_SYSTEM
 async with httpx.AsyncClient(timeout=120,trust_env=False) as client:
  r=await client.post('http://127.0.0.1:11434/api/chat',json={
   'model':'qwen3:4b','stream':False,'think':False,
   'format':psb_engine.PLAN_SCHEMA if planner else psb_engine.SCHEMA,
   'options':{'temperature':0,'num_ctx':24576,'num_predict':1000 if planner else 1800},
   'messages':[{'role':'system','content':kwargs.get('system',psb_engine.SYSTEM)},
               {'role':'user','content':value}]})
  r.raise_for_status()
  return r.json()['message']['content']
solution.generate_remote=generate
asyncio.run(solution.main())
'''

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--archive',type=Path,required=True)
    parser.add_argument('--ids',default='9')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp);data=root/'data';data.mkdir()
        with ZipFile(args.archive) as z:z.extractall(root/'run')
        with ZipFile(data/'knowledge_base.zip','w') as z:
            for p in (ROOT/'backend/psb_data/knowledge-base').glob('*.txt'):z.write(p,p.name)
        with (ROOT/'backend/psb_data/demo_questions.csv').open(encoding='utf-8-sig') as stream:
            rows=[r for r in csv.DictReader(stream) if r['id'] in args.ids.split(',')]
        if not rows:raise ValueError('No selected questions')
        with (data/'questions.csv').open('w',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=['id','question']);writer.writeheader();writer.writerows(rows)
        report=root/'diagnostics.json'
        process=subprocess.run([sys.executable,'-X','utf8','-c',CODE],cwd=root/'run',env={**os.environ,
            'DATA_DIR':str(data),'RAG_SEMANTIC':'0','MAX_WORKERS':'1','PSB_DIAGNOSTICS_PATH':str(report)},
            capture_output=True,text=True,encoding='utf-8',timeout=1100)
        if process.returncode:raise RuntimeError(process.stderr)
        with (root/'run/submission.csv').open(encoding='utf-8') as stream:answers=list(csv.DictReader(stream))
        result={'archive':args.archive.name,'model':'qwen3:4b','thinking':False,'semantic':False,
                'answers':answers,'diagnostics':json.loads(report.read_text(encoding='utf-8')) if report.exists() else None,
                'stderr':process.stderr}
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(result,ensure_ascii=False,indent=2))
