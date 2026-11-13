"""Прогон демовопросов на Ollama. Эталоны не передаются модели."""
import asyncio
import argparse
import csv
import json
from pathlib import Path
import sys
import time
import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
from psb_engine import KnowledgeBase, SYSTEM, SCHEMA, checked_answer

async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--ids',default='',help='ID через запятую; пусто — все демовопросы')
    parser.add_argument('--output',default='dist/local-evaluation-v3.json')
    parser.add_argument('--model',default='qwen3:4b')
    args=parser.parse_args()
    kb=KnowledgeBase.from_path(ROOT/'backend/psb_data/knowledge-base')
    questions=list(csv.DictReader((ROOT/'backend/psb_data/demo_questions.csv').open(encoding='utf-8-sig')))
    if args.ids: questions=[q for q in questions if q['id'] in args.ids.split(',')]
    results=[]
    output=ROOT/args.output
    output.parent.mkdir(exist_ok=True)
    async with httpx.AsyncClient(timeout=180,trust_env=False) as client:
        raw_responses=[]
        async def generate(value):
            r=await client.post('http://127.0.0.1:11434/api/chat',json={'model':args.model,'stream':False,'think':True,'format':SCHEMA,'options':{'temperature':0,'num_ctx':24576,'num_predict':5000},'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':value}]})
            r.raise_for_status()
            content=r.json()['message']['content']
            raw_responses.append(content)
            return content
        for row in questions:
            raw_responses.clear()
            start=time.monotonic()
            try:
                result=await checked_answer(row['question'],[],kb.search(row['question']),generate,kb.catalog)
                out={'id':row['id'],'status':result['status'],'answer':result['answer'],'sources':len(result['sources'])}
            except Exception as exc:out={'id':row['id'],'error':str(exc)}
            out['seconds']=round(time.monotonic()-start,1);results.append(out)
            out['raw_responses']=list(raw_responses)
            output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({k:v for k,v in out.items() if k!='raw_responses'},ensure_ascii=False),flush=True)
    print('Report:',output)

if __name__=='__main__':asyncio.run(main())
