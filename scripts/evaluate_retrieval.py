"""Проверяет наличие необходимых выдержек в контексте, а не правильность ответа LLM."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import asyncio
import os

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', default=str(ROOT/'backend/psb_engine.py'))
    parser.add_argument('--output')
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--semantic-model',help='Локальная embedding-модель Ollama для проверки того же API-пути')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('evaluated_engine', args.engine)
    engine = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = engine
    spec.loader.exec_module(engine)
    kb = engine.KnowledgeBase.from_path(ROOT/'backend/psb_data/knowledge-base')
    hints={}
    if args.semantic_model:
        sys.path.insert(0,str(ROOT/'backend'))
        from psb_retrieval import RemoteRetrieval
        os.environ.update(LLM_BASE_URL='http://127.0.0.1:11434/v1',LLM_API_KEY='local-ollama',EMB_MODEL=args.semantic_model)
        async def prepare_hints():
            retrieval=RemoteRetrieval(kb)
            if not await retrieval.prepare():raise RuntimeError('Semantic index unavailable')
            return {case['id']:await retrieval.hints(case['question']) for case in cases}
    cases = json.loads((ROOT/'tests/fixtures/retrieval_cases.json').read_text(encoding='utf-8'))
    if args.semantic_model:hints=asyncio.run(prepare_hints())
    norm = lambda value: ' '.join(value.lower().replace('ё','е').split())
    results = []
    for case in cases:
        # Сначала проверяем саму разметку: ожидаемая выдержка действительно есть в корпусе.
        corpus = '\n'.join(d['text'] for d in kb.documents.values() if case['document'] in d['title'])
        assert all(norm(n) in norm(corpus) for n in case['needles']), case['id']+' invalid fixture'
        sources = kb.search(case['question'],**({'preferred_fragments':hints[case['id']].get('fragments',[])} if hints else {}))
        context = '\n'.join(f.text for f in sources if case['document'] in f.title)
        missing = [n for n in case['needles'] if norm(n) not in norm(context)]
        results.append({'id':case['id'],'pass':not missing,'missing':missing,'context_chars':sum(len(f.text) for f in sources)})
    print(json.dumps(results,ensure_ascii=False,indent=2))
    print('Complete context:',sum(r['pass'] for r in results),'/',len(results))
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.check and not all(r['pass'] for r in results): raise SystemExit(1)


if __name__ == '__main__': main()
