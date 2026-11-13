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
from psb_engine import KnowledgeBase, SYSTEM, SCHEMA, PLANNER_SYSTEM, PLAN_SCHEMA, answer_question

async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--ids',default='',help='ID через запятую; пусто — все демовопросы')
    parser.add_argument('--output',default='dist/local-evaluation-v4.json')
    parser.add_argument('--model',default='qwen3:4b')
    parser.add_argument('--questions',default='backend/psb_data/demo_questions.csv')
    parser.add_argument('--no-plan',action='store_true')
    args=parser.parse_args()
    kb=KnowledgeBase.from_path(ROOT/'backend/psb_data/knowledge-base')
    source=ROOT/args.questions
    questions=json.loads(source.read_text(encoding='utf-8')) if source.suffix=='.json' else list(csv.DictReader(source.open(encoding='utf-8-sig')))
    if args.ids: questions=[q for q in questions if q['id'] in args.ids.split(',')]
    results=[]
    output=ROOT/args.output
    output.parent.mkdir(exist_ok=True)
    async with httpx.AsyncClient(timeout=180,trust_env=False) as client:
        raw_responses=[]
        raw_plans=[]
        async def planner(value):
            r=await client.post('http://127.0.0.1:11434/api/chat',json={'model':args.model,'stream':False,'think':False,'format':PLAN_SCHEMA,'options':{'temperature':0,'num_ctx':24576,'num_predict':1000},'messages':[{'role':'system','content':PLANNER_SYSTEM},{'role':'user','content':value}]})
            r.raise_for_status()
            content=r.json()['message']['content'];raw_plans.append(content)
            return content
        async def generate(value):
            r=await client.post('http://127.0.0.1:11434/api/chat',json={'model':args.model,'stream':False,'think':True,'format':SCHEMA,'options':{'temperature':0,'num_ctx':24576,'num_predict':5000},'messages':[{'role':'system','content':SYSTEM},{'role':'user','content':value}]})
            r.raise_for_status()
            content=r.json()['message']['content']
            raw_responses.append(content)
            return content
        for row in questions:
            raw_responses.clear()
            raw_plans.clear()
            start=time.monotonic()
            try:
                result=await asyncio.wait_for(answer_question(kb,row['question'],[],generate,None if args.no_plan else planner),timeout=180)
                out={'id':row['id'],'status':result['status'],'answer':result['answer'],'sources':len(result['sources'])}
            except Exception as exc:out={'id':row['id'],'error':str(exc)}
            out['seconds']=round(time.monotonic()-start,1);results.append(out)
            out['raw_responses']=list(raw_responses)
            out['retrieval_plans']=list(raw_plans)
            output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({k:v for k,v in out.items() if k not in {'raw_responses','retrieval_plans'}},ensure_ascii=False),flush=True)
    print('Report:',output)

if __name__=='__main__':asyncio.run(main())
