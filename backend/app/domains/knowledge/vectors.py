"""Отдельная коллекция пользовательских источников, с обязательным фильтром владельца."""
import hashlib
import uuid
import httpx


class VectorIndex:
    def __init__(self,settings):
        self.url=settings.qdrant_url.rstrip('/')
        self.collection='psb_uploads_'+hashlib.sha256(settings.ollama_embed_model.encode()).hexdigest()[:10]

    async def ensure(self,size):
        async with httpx.AsyncClient(timeout=30,trust_env=False) as client:
            path=f'{self.url}/collections/{self.collection}'
            r=await client.get(path)
            if r.status_code==404:
                r=await client.put(path,json={'vectors':{'size':size,'distance':'Cosine'}})
            r.raise_for_status()

    async def upsert(self,owner_id,document_id,items,vectors):
        if len(items)!=len(vectors) or not vectors: raise ValueError('Некорректный ответ модели индексации.')
        points=[{'id':str(uuid.uuid5(uuid.NAMESPACE_URL,f'psb:{owner_id}:{document_id}:{item[0]}')),
                 'vector':vector,'payload':{'owner_id':owner_id,'document_id':document_id,'fragment_id':item[1]}}
                for item,vector in zip(items,vectors)]
        async with httpx.AsyncClient(timeout=60,trust_env=False) as client:
            r=await client.put(f'{self.url}/collections/{self.collection}/points',params={'wait':'true'},json={'points':points})
            r.raise_for_status()

    async def search(self,owner_id,document_ids,vector):
        if not document_ids: return []
        async with httpx.AsyncClient(timeout=15,trust_env=False) as client:
            r=await client.post(f'{self.url}/collections/{self.collection}/points/query',json={
                'query':vector,'limit':12,'with_payload':True,
                'filter':{'must':[{'key':'owner_id','match':{'value':owner_id}},
                                  {'key':'document_id','match':{'any':document_ids}}]}})
            r.raise_for_status()
            return [p['payload'] for p in r.json()['result']['points']]

    async def delete(self,owner_id,document_id):
        async with httpx.AsyncClient(timeout=15,trust_env=False) as client:
            r=await client.post(f'{self.url}/collections/{self.collection}/points/delete',params={'wait':'true'},json={
                'filter':{'must':[{'key':'owner_id','match':{'value':owner_id}},
                                  {'key':'document_id','match':{'value':document_id}}]}})
            if r.status_code!=404: r.raise_for_status()
