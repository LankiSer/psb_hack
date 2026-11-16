"""Сравнение полного RAG и генерации на заранее проверенных источниках."""
import argparse
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import time
import httpx

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))


async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--engine',default='experiments/v11/psb_engine.py')
    parser.add_argument('--split',choices=['dev','holdout'],default='dev')
    parser.add_argument('--modes',default='full,oracle')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    spec=importlib.util.spec_from_file_location('component_engine',ROOT/args.engine)
    engine=importlib.util.module_from_spec(spec);sys.modules[spec.name]=engine;spec.loader.exec_module(engine)
    kb=engine.KnowledgeBase.from_path(ROOT/'backend/psb_data/knowledge-base')
    cases=json.loads((ROOT/'tests/fixtures/independent_cases.json').read_text(encoding='utf-8'))
    cases=[c for c in cases if c['split']==args.split]
    args.output.parent.mkdir(parents=True,exist_ok=True)
    report=[]
    norm=lambda s:' '.join(s.casefold().replace('ё','е').split())
    async with httpx.AsyncClient(timeout=150,trust_env=False) as client:
        # Проверка соединения не допускает бессодержательного "успешного" прогона без модели.
        (await client.get('http://127.0.0.1:11434/api/tags')).raise_for_status()
        for case in cases:
            oracle=[]
            for i,item in enumerate(case['evidence']):
                doc=next(d for d in kb.documents.values() if d['title']==item['title'])
                assert doc['text'].splitlines()[item['line']-1]==item['quote']
                oracle.append(engine.Fragment(doc['id']+f'-gold-{i}',doc['id'],doc['title'],doc['category'],
                    item['line'],item['line'],item['quote']))
            for mode in args.modes.split(','):
                calls=[];contexts=[]
                async def invoke(value,planner=False):
                    data,_=json.JSONDecoder().raw_decode(value)
                    if not planner:contexts.append(data['sources'])
                    response=await client.post('http://127.0.0.1:11434/api/chat',json={
                        'model':'qwen3:4b','stream':False,'think':False,
                        'format':engine.PLAN_SCHEMA if planner else engine.SCHEMA,
                        'options':{'temperature':0,'num_ctx':24576,'num_predict':1000 if planner else 1800},
                        'messages':[{'role':'system','content':engine.PLANNER_SYSTEM if planner else engine.SYSTEM},
                                    {'role':'user','content':value}]})
                    response.raise_for_status();calls.append('plan' if planner else 'answer')
                    return response.json()['message']['content']
                async def generate(value):return await invoke(value)
                async def planner(value):return await invoke(value,True)
                start=time.monotonic()
                entry={'id':case['id'],'mode':mode}
                try:
                    if mode=='full':
                        call=engine.answer_question(kb,case['question'],[],generate,planner)
                    elif mode=='oracle':
                        call=engine.checked_answer(case['question'],[],oracle,generate,kb.catalog)
                    else:raise ValueError('Unknown mode')
                    result=await asyncio.wait_for(call,timeout=180)
                    entry.update(answer=result['answer'],status=result['status'])
                except Exception as error:
                    entry.update(error=type(error).__name__,detail=str(error))
                context=contexts[0] if contexts else []
                entry['missing_evidence']=[e['quote'] for e in case['evidence'] if not any(
                    s['title']==e['title'] and norm(e['quote']) in norm(s['text']) for s in context)]
                entry.update(seconds=round(time.monotonic()-start,2),calls=calls,
                             context_chars=sum(len(s['text']) for s in context))
                report.append(entry)
                args.output.write_text(json.dumps({'engine':args.engine,'split':args.split,'model':'qwen3:4b',
                    'thinking':False,'semantic':False,'results':report},ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps({k:v for k,v in entry.items() if k not in {'answer','detail','missing_evidence'}},ensure_ascii=False),flush=True)


if __name__=='__main__':asyncio.run(main())
