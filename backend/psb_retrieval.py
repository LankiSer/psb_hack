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
        if not self.vectors:
            return {}
        history,current = split_dialogue(question)
        previous = '\n'.join(m['text'] for m in history[-4:] if m['role']=='user')
        query = (previous[-1500:]+'\n'+current)[-4000:]
        try:
            async with httpx.AsyncClient(timeout=8,trust_env=self.trust_env) as client:
                vector = (await self.embed(client,[query]))[0]
            if len(vector) != len(self.vectors[0]):
                raise ValueError('Query embedding dimension mismatch')
            scores = [sum(a*b for a,b in zip(vector,v)) for v in self.vectors]
            ranked = sorted(range(len(scores)),key=scores.__getitem__,reverse=True)[:8]
            # Это кандидаты, а не подтверждение факта: итог проходит обычную проверку источников.
            return {'fragments':[self.fragments[i].id for i in ranked]}
        except (httpx.HTTPError,ValueError,KeyError,TypeError,TimeoutError):
            return {}
