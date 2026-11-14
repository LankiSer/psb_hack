"""Необязательный семантический поиск через совместимый API платформы."""
import asyncio
import math
import os
import sys
from urllib.parse import urlsplit

import httpx

from psb_engine import env, split_dialogue


class RemoteRetrieval:
    def __init__(self, kb):
        self.kb = kb
        self.fragments = list(kb.fragments)
        self.vectors = []
        self.base = env('LLM_BASE_URL', 'OPENAI_BASE_URL', 'BASE_URL').rstrip('/')
        self.key = env('LLM_API_KEY', 'OPENAI_API_KEY')
        self.model = env('EMB_MODEL') or 'BAAI/bge-m3'
        self.reranker = env('RERANKER_MODEL') or 'Qwen/Qwen3-Reranker-8B'
        self.rerank_available = None
        self.rerank_probe = asyncio.Lock()
        self.trust_env = urlsplit(self.base).hostname not in {'localhost','127.0.0.1','::1'}

    @staticmethod
    def normalize(vector):
        if not isinstance(vector, list) or not vector or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in vector):
            raise ValueError('Invalid embedding')
        length = math.sqrt(sum(x*x for x in vector))
        if not length:
            raise ValueError('Empty embedding')
        return [x/length for x in vector]

    async def embed(self, client, texts):
        for attempt in range(2):
            response = await client.post(self.base+'/embeddings', headers={'Authorization':'Bearer '+self.key},
                                         json={'model':self.model,'input':texts})
            if response.status_code not in {429,500,502,503,504} or attempt:
                break
            await asyncio.sleep(1)
        response.raise_for_status()
        data = response.json()['data']
        if len(data) != len(texts) or sorted(row['index'] for row in data) != list(range(len(texts))):
            raise ValueError('Incomplete embedding batch')
        vectors = [self.normalize(row['embedding']) for row in sorted(data,key=lambda row:row['index'])]
        if len({len(v) for v in vectors}) != 1:
            raise ValueError('Embedding dimension mismatch')
        return vectors

    async def prepare(self):
        # При отсутствии параметров платформы не угадываем адреса и не загружаем веса.
        if not all((self.base,self.key,self.model)) or os.environ.get('RAG_SEMANTIC','1') == '0':
            return False
        async def index():
            async with httpx.AsyncClient(timeout=20,trust_env=self.trust_env) as client:
                vectors = []
                for start in range(0,len(self.fragments),32):
                    texts = [(f.title+'\n'+f.heading+'\n'+f.text)[:7000] for f in self.fragments[start:start+32]]
                    vectors.extend(await self.embed(client,texts))
                if len({len(v) for v in vectors}) != 1:
                    raise ValueError('Embedding dimension changed')
                return vectors
        try:
            self.vectors = await asyncio.wait_for(index(),timeout=60)
            return bool(self.vectors)
        except (httpx.HTTPError,ValueError,KeyError,TypeError,TimeoutError) as exc:
            code=exc.response.status_code if isinstance(exc,httpx.HTTPStatusError) else type(exc).__name__
            print(f'Embedding index unavailable: {code}',file=sys.stderr,flush=True)
            self.vectors = []
            return False

    async def hints(self, question):
        history,current = split_dialogue(question)
        previous = '\n'.join(m['text'] for m in history[-4:] if m['role']=='user')
        query = (previous[-1500:]+'\n'+current)[-4000:]
        dense = []
        if self.vectors:
            try:
                async with httpx.AsyncClient(timeout=8,trust_env=self.trust_env) as client:
                    vector = (await self.embed(client,[query]))[0]
                if len(vector) != len(self.vectors[0]):
                    raise ValueError('Query embedding dimension mismatch')
                scores = [sum(a*b for a,b in zip(vector,v)) for v in self.vectors]
                ranked = sorted(range(len(scores)),key=scores.__getitem__,reverse=True)[:40]
                dense = [self.fragments[i] for i in ranked]
            except (httpx.HTTPError,ValueError,KeyError,TypeError,TimeoutError):
                pass
        hints = {'fragments':[f.id for f in dense[:8]]} if dense else {}
        # По умолчанию выключен: на платформе реранкер не дал прироста и чуть снизил балл.
        if not self.base or not self.key or self.rerank_available is False or os.environ.get('RAG_RERANK','0') == '0':
            return hints
        candidates = self.candidates(question,dense)
        if not candidates: return hints
        try:
            # Проверяем совместимость единожды; остальные вопросы не повторяют заведомый 404.
            if self.rerank_available is None:
                async with self.rerank_probe:
                    if self.rerank_available is None:
                        ordered = await self.rerank(query,candidates)
                    elif self.rerank_available is False:
                        return hints
                    else:
                        ordered = await self.rerank(query,candidates)
            else:
                ordered = await self.rerank(query,candidates)
            if ordered:
                hints['ranked_fragments'] = ordered
                # Обеспечиваем включение смысловых совпадений даже без общих слов.
                hints['fragments'] = list(dict.fromkeys(ordered+hints.get('fragments',[])))
        except (httpx.HTTPError,ValueError,KeyError,TypeError,TimeoutError):
            pass
        return hints

    def candidates(self, question, dense):
        lexical = self.kb.search(question,limit=80,raw=True)
        by_id = {f.id:f for f in lexical+dense}
        # RRF не смешивает несопоставимые абсолютные оценки BM25 и cosine.
        scores = {}
        for ranking in (lexical,dense):
            for i,f in enumerate(ranking):scores[f.id]=scores.get(f.id,0)+1/(60+i+1)
        order = sorted(scores,key=scores.get,reverse=True)
        # Резервируем места для разных документов: длинная статья не вытесняет весь корпус.
        chosen=[];docs=set()
        for key in order:
            f=by_id[key]
            if f.document_id not in docs:
                chosen.append(key);docs.add(f.document_id)
            if len(chosen)>=16:break
        chosen=list(dict.fromkeys(order[:16]+chosen+order))[:40]
        return [by_id[key] for key in chosen]

    async def rerank(self, query, candidates):
        async with httpx.AsyncClient(timeout=20,trust_env=self.trust_env) as client:
            response = await client.post(self.base+'/rerank',headers={'Authorization':'Bearer '+self.key},json={
                'model':self.reranker,'query':query,'documents':[f.title+'\n'+f.heading+'\n'+f.text for f in candidates],
                'top_n':min(12,len(candidates)),'return_documents':False})
        if response.status_code in {400,401,403,404,405,422}:
            self.rerank_available=False
            print(f'Rerank unavailable: {response.status_code}; using hybrid fallback',file=sys.stderr,flush=True)
            return []
        response.raise_for_status()
        results=response.json()['results']
        if not isinstance(results,list) or not results:raise ValueError('Empty rerank response')
        seen=set();ordered=[]
        for row in sorted(results,key=lambda r:float(r['relevance_score']),reverse=True):
            index=row['index'];score=float(row['relevance_score'])
            if isinstance(index,bool) or not isinstance(index,int) or not 0<=index<len(candidates) or index in seen or not math.isfinite(score):
                raise ValueError('Invalid rerank result')
            seen.add(index);ordered.append(candidates[index].id)
        self.rerank_available=True
        return ordered[:12]
