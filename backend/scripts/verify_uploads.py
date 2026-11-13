"""Контракт загрузки/API на временной БД; эмбеддинги и Qdrant подменены только в этом тесте."""
import asyncio
import io
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile


def main():
    with tempfile.TemporaryDirectory() as tmp:
        os.environ['DATA_DIR']=tmp
        from fastapi.testclient import TestClient
        from app.main import app
        from app.api.psb_deps import get_current_user,get_upload_service,get_ollama
        from app.config import Settings
        from app.shared.db import Base,SessionLocal,engine
        from app.domains.knowledge.service import UploadService
        from app.domains.knowledge.models import KnowledgeUpload
        from app.domains.knowledge.parsing import parse_document
        from pypdf import PdfWriter
        Base.metadata.create_all(engine)

        class Embeddings:
            async def embed(self,texts): return [[1.0,0.0] for _ in texts]
        class Index:
            def __init__(self): self.points=[];self.fail=False;self.queries=[]
            async def ensure(self,size):
                assert size==2
                if self.fail: raise RuntimeError('test offline')
            async def upsert(self,owner,doc,items,vectors):
                self.points += [{'owner_id':owner,'document_id':doc,'fragment_id':i[1]} for i in items]
            async def search(self,owner,ids,vector):
                self.queries.append(owner)
                # Даже при лишнем чужом payload сервис обязан повторно проверить владельца.
                return self.points+[{'owner_id':999,'document_id':'foreign','fragment_id':'foreign'}]
            async def delete(self,owner,doc): self.points=[p for p in self.points if not(p['owner_id']==owner and p['document_id']==doc)]
        class Chat:
            async def chat(self,system,prompt,**kwargs):
                data=json.loads(prompt)
                if 'sources' not in data: return json.dumps({'queries':[],'documents':[]})
                source=next(s for s in data['sources'] if 'Флюоритовый' in s['text'])
                return json.dumps({'status':'answer','answer':'Ответ по новому документу ['+source['id']+']','evidence':[]})

        index=Index();service=UploadService(Settings(data_dir=tmp,max_upload_bytes=1024*1024),SessionLocal,Embeddings(),index)
        app.dependency_overrides[get_upload_service]=lambda:service
        app.dependency_overrides[get_ollama]=lambda:Chat()
        client=TestClient(app)
        assert client.get('/api/knowledge/uploads').status_code==401
        app.dependency_overrides[get_current_user]=lambda:SimpleNamespace(id=1)
        raw='Договор поставки\nФлюоритовый договор: доступ к помещению круглосуточно.'.encode()
        response=client.post('/api/knowledge/uploads',files={'file':('../../Договор.txt',raw,'text/plain')})
        assert response.status_code==202,response.text
        row=response.json();assert row['status']=='queued' and row['filename']=='Договор.txt'
        duplicate=client.post('/api/knowledge/uploads',files={'file':('Копия.txt',raw,'text/plain')}).json()
        assert duplicate['id']==row['id'] and duplicate['duplicate']
        assert len(client.get('/api/knowledge/documents').json())==21
        asyncio.run(service.process(row['id']))
        row=client.get('/api/knowledge/uploads').json()[0]
        assert row['status']=='ready' and row['progress']==100 and row['kind']=='Договор',row
        assert index.points and row['chunk_count']>0
        doc=client.get('/api/knowledge/documents/'+row['document_id']).json()
        assert 'Флюоритовый' in doc['text']
        answer=client.post('/api/knowledge/ask',json={'question':'Где доступ к помещению?'}).json()
        assert any(s['document_id']==row['document_id'] for s in answer['sources']),answer
        assert index.queries==[1]
        assert client.get('/api/knowledge/uploads/'+row['id']+'/download').content==raw
        app.dependency_overrides[get_current_user]=lambda:SimpleNamespace(id=2)
        assert client.get('/api/knowledge/uploads').json()==[]
        assert client.get('/api/knowledge/documents/'+row['document_id']).status_code==404
        for method,path in [('get','/download'),('post','/retry'),('delete','')]:
            assert getattr(client,method)('/api/knowledge/uploads/'+row['id']+path).status_code==404
        app.dependency_overrides[get_current_user]=lambda:SimpleNamespace(id=1)
        bad=client.post('/api/knowledge/uploads',files={'file':('wrong.pdf',b'not a pdf document','application/pdf')}).json()
        asyncio.run(service.process(bad['id']))
        assert next(x for x in service.list(1) if x['id']==bad['id'])['status']=='error'
        assert client.post('/api/knowledge/uploads/'+bad['id']+'/retry').status_code==200
        assert client.post('/api/knowledge/uploads',files={'file':('bad.exe',b'hello','application/octet-stream')}).status_code==422
        assert client.post('/api/knowledge/uploads',files={'file':('large.txt',b'x'*(1024*1024+1),'text/plain')}).status_code==413
        assert client.delete('/api/knowledge/uploads/'+row['id']).status_code==204
        assert not index.points and not service.path(row['id']).exists()
        assert client.get('/api/knowledge/documents/'+row['document_id']).status_code==404
        # Сбой внешнего индекса не делает документ готовым. Повтор сохраняет один документ.
        fresh=service.add(1,'Регламент.txt','Регламент\nДокумент для проверки повторной индексации.'.encode())
        index.fail=True;asyncio.run(service.process(fresh['id']))
        assert next(r for r in service.list(1) if r['id']==fresh['id'])['status']=='error'
        index.fail=False;service.retry(1,fresh['id']);asyncio.run(service.process(fresh['id']))
        assert next(r for r in service.list(1) if r['id']==fresh['id'])['status']=='ready'
        # Восстановление прерванного задания после перезапуска worker.
        resumed=service.add(1,'Продолжение.txt','Документ\nОчередь должна продолжить обработку после перезапуска.'.encode())
        service.change(resumed['id'],status='parsing')
        async def recover():
            task=asyncio.create_task(service.run())
            try:
                for _ in range(100):
                    if next(r for r in service.list(1) if r['id']==resumed['id'])['status']=='ready': return
                    await asyncio.sleep(.02)
                raise AssertionError('Worker did not recover')
            finally:
                task.cancel()
                try: await task
                except asyncio.CancelledError: pass
        asyncio.run(recover())
        # DOCX и пустой PDF: поддержанный формат и явная ошибка вместо пустого источника.
        buffer=io.BytesIO()
        with ZipFile(buffer,'w') as z:
            z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Договор: тестовый текст документа DOCX.</w:t></w:r></w:p></w:body></w:document>')
        assert 'тестовый' in parse_document(buffer.getvalue(),'Тест.docx')[0]
        writer=PdfWriter();writer.add_blank_page(width=100,height=100);pdf=io.BytesIO();writer.write(pdf)
        try: parse_document(pdf.getvalue(),'Скан.pdf');raise AssertionError('Accepted empty scan')
        except ValueError as exc: assert 'OCR' in str(exc)
        app.dependency_overrides.clear();client.close();engine.dispose()
        print('PASS: upload, deduplication, queue, parsing, indexing, RAG citation, owner isolation, download, deletion, retry, restart recovery, DOCX/PDF limits (mock vector transport).')


if __name__=='__main__': main()
