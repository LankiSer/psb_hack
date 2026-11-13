"""Проверка реальных Ollama/Qdrant без аккаунта и пользовательских документов."""
import asyncio
import uuid
import httpx
from app.config import get_settings
from app.shared.ollama.client import OllamaClient
from app.domains.knowledge.vectors import VectorIndex


async def main():
    settings=get_settings();embedder=OllamaClient(settings);index=VectorIndex(settings)
    index.collection='psb_acceptance_'+uuid.uuid4().hex
    try:
        vectors=await embedder.embed(['search_document: Тестовый архив открыт по будням с девяти до восемнадцати часов.'])
        await index.ensure(len(vectors[0]))
        await index.upsert(990001,'test-document',[(0,'test-fragment','')],vectors)
        query=(await embedder.embed(['search_query: В какое время работает архив?']))[0]
        found=await index.search(990001,['test-document'],query)
        assert found and found[0]['fragment_id']=='test-fragment'
        assert not await index.search(990002,['test-document'],query)
        await index.delete(990001,'test-document')
        assert not await index.search(990001,['test-document'],query)
        print(f'PASS: real embeddings ({len(query)} dimensions), upsert, vector query, owner filter, deletion. No account created.')
    finally:
        async with httpx.AsyncClient(timeout=20,trust_env=False) as client:
            result=await client.delete(f'{index.url}/collections/{index.collection}')
            if result.status_code not in (200,404): result.raise_for_status()


if __name__=='__main__': asyncio.run(main())
