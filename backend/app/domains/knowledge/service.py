import asyncio
import hashlib
import logging
import uuid
from pathlib import Path
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError
from app.domains.knowledge.models import KnowledgeUpload
from app.domains.knowledge.parsing import parse_document, SUPPORTED
from app.domains.knowledge.vectors import VectorIndex
from app.shared.ollama.client import OllamaClient
from psb_engine import KnowledgeBase

logger=logging.getLogger(__name__)


class UploadService:
    def __init__(self,settings,sessions,embedder=None,index=None):
        self.settings=settings
        self.sessions=sessions
        self.embedder=embedder or OllamaClient(settings)
        self.index=index or VectorIndex(settings)
        self.root=settings.data_path/'knowledge_uploads'

    def path(self,upload_id):
        return self.root/(str(uuid.UUID(upload_id))+'.bin')

    def list(self,owner_id):
        with self.sessions() as db:
            return [r.public() for r in db.scalars(select(KnowledgeUpload).where(KnowledgeUpload.owner_id==owner_id,KnowledgeUpload.status!='deleted').order_by(KnowledgeUpload.created_at.desc()))]

    def add(self,owner_id,filename,raw):
        filename=Path(filename.replace('\\','/')).name[:240]
        if Path(filename).suffix.lower() not in SUPPORTED: raise ValueError('Поддерживаются PDF, DOCX, TXT и MD.')
        if not raw: raise ValueError('Файл пуст.')
        if len(raw)>self.settings.max_upload_bytes: raise ValueError('Максимальный размер файла — 25 МБ.')
        checksum=hashlib.sha256(raw).hexdigest()
        with self.sessions() as db:
            row=db.scalar(select(KnowledgeUpload).where(KnowledgeUpload.owner_id==owner_id,KnowledgeUpload.sha256==checksum))
            if row and row.status!='deleted': return {**row.public(),'duplicate':True}
            count=db.scalar(select(func.count()).select_from(KnowledgeUpload).where(KnowledgeUpload.owner_id==owner_id,KnowledgeUpload.status!='deleted'))
            if count>=100: raise ValueError('Можно хранить до 100 загруженных документов. Удалите ненужные файлы.')
            if row:
                row.status='queued';row.error='';row.progress=0;row.filename=filename
            else:
                row=KnowledgeUpload(id=str(uuid.uuid4()),owner_id=owner_id,filename=filename,sha256=checksum,size=len(raw),status='queued')
                db.add(row)
            self.root.mkdir(parents=True,exist_ok=True)
            self.path(row.id).write_bytes(raw)
            try: db.commit()
            except IntegrityError:
                # Одновременная загрузка одинаковых файлов не создаёт дубль.
                orphan=row.id;db.rollback();self.path(orphan).unlink(missing_ok=True)
                existing=db.scalar(select(KnowledgeUpload).where(KnowledgeUpload.owner_id==owner_id,KnowledgeUpload.sha256==checksum))
                if not existing: raise
                return {**existing.public(),'duplicate':True}
            db.refresh(row)
            return row.public()

    def owned(self,db,owner_id,upload_id):
        row=db.scalar(select(KnowledgeUpload).where(KnowledgeUpload.id==upload_id,KnowledgeUpload.owner_id==owner_id,KnowledgeUpload.status!='deleted'))
        if row is None: raise LookupError('Документ не найден.')
        return row

    def retry(self,owner_id,upload_id):
        with self.sessions() as db:
            row=self.owned(db,owner_id,upload_id)
            if row.status!='error': raise ValueError('Документ уже обрабатывается или готов к поиску.')
            row.status='queued';row.error='';row.progress=0;db.commit();db.refresh(row)
            return row.public()

    async def delete(self,owner_id,upload_id):
        with self.sessions() as db:
            row=self.owned(db,owner_id,upload_id);document_id=row.document_id
            row.status='deleted';row.text='';db.commit()
        self.path(upload_id).unlink(missing_ok=True)
        try: await self.index.delete(owner_id,document_id)
        except Exception: logger.warning('Deferred vector cleanup for deleted upload %s',upload_id)

    def ready_documents(self,owner_id):
        with self.sessions() as db:
            rows=list(db.scalars(select(KnowledgeUpload).where(KnowledgeUpload.owner_id==owner_id,KnowledgeUpload.status=='ready')))
            return [(r.storage_name,r.text) for r in rows]

    def make_knowledge(self,base_dir,owner_id):
        documents=[(p.name,p.read_text(encoding='utf-8-sig')) for p in base_dir.glob('*.txt')]
        return KnowledgeBase(documents+self.ready_documents(owner_id))

    async def hints(self,owner_id,question):
        with self.sessions() as db:
            ids=list(db.scalars(select(KnowledgeUpload.document_id).where(KnowledgeUpload.owner_id==owner_id,KnowledgeUpload.status=='ready')))
        if not ids: return {},''
        try:
            prefix='search_query: ' if self.settings.ollama_embed_model.startswith('nomic') else ''
            vectors=await asyncio.wait_for(self.embedder.embed([prefix+question]),timeout=20)
            matches=await self.index.search(owner_id,ids,vectors[0])
            # Дополнительная проверка не позволяет подмешать чужой payload даже при ошибке индекса.
            matches=[m for m in matches if m.get('owner_id')==owner_id and m.get('document_id') in ids]
            return {'documents':list({m['document_id'] for m in matches}),'fragments':list({m['fragment_id'] for m in matches})},''
        except Exception:
            return {},'Поиск по смыслу временно недоступен. Использован поиск по тексту документов.'

    def change(self,upload_id,**values):
        with self.sessions() as db:
            count=db.execute(update(KnowledgeUpload).where(KnowledgeUpload.id==upload_id,KnowledgeUpload.status!='deleted').values(**values)).rowcount
            db.commit()
            return bool(count)

    async def process(self,upload_id):
        with self.sessions() as db:
            claimed=db.execute(update(KnowledgeUpload).where(KnowledgeUpload.id==upload_id,KnowledgeUpload.status=='queued').values(status='parsing',progress=5,error='')).rowcount
            db.commit()
            if not claimed: return
            row=db.get(KnowledgeUpload,upload_id);owner_id=row.owner_id;filename=row.filename
        stage='parsing'
        try:
            raw=await asyncio.to_thread(self.path(upload_id).read_bytes)
            text,kind=await asyncio.to_thread(parse_document,raw,filename)
            name=('законы' if kind=='Нормативный акт' else 'загрузка')+'_'+upload_id+'__'+Path(filename).stem+'.txt'
            kb=KnowledgeBase([(name,text)])
            document_id=next(iter(kb.documents))
            if not self.change(upload_id,status='embedding',progress=15,text=text,kind=kind,storage_name=name,document_id=document_id): return
            stage='embedding';items=[]
            for fragment in kb.fragments:
                for offset in range(0,len(fragment.text),1100):
                    items.append((len(items),fragment.id,fragment.title+'\n'+fragment.text[offset:offset+1200]))
            if len(items)>1500: raise ValueError('Слишком большой документ для индексации. Разделите его на части.')
            prefix='search_document: ' if self.settings.ollama_embed_model.startswith('nomic') else ''
            for start in range(0,len(items),16):
                batch=items[start:start+16]
                vectors=await self.embedder.embed([prefix+i[2] for i in batch])
                if start==0: await self.index.ensure(len(vectors[0]))
                await self.index.upsert(owner_id,document_id,batch,vectors)
                if not self.change(upload_id,progress=15+int(80*(start+len(batch))/len(items))): return
            self.change(upload_id,status='ready',progress=100,chunk_count=len(items),error='')
        except asyncio.CancelledError:
            self.change(upload_id,status='queued',progress=0)
            raise
        except Exception as exc:
            message=str(exc) if isinstance(exc,ValueError) else ('Не удалось прочитать файл. Проверьте его целостность.' if stage=='parsing' else 'Сервис индексации недоступен. Проверьте Ollama и Qdrant, затем повторите обработку.')
            self.change(upload_id,status='error',error=message[:500],progress=0)
            logger.warning('Upload %s failed at %s: %s',upload_id,stage,type(exc).__name__)

    async def run(self):
        # Очередь хранится в SQLite. Поддерживается один процесс worker в составе приложения.
        with self.sessions() as db:
            db.execute(update(KnowledgeUpload).where(KnowledgeUpload.status.in_(['parsing','embedding'])).values(status='queued',progress=0));db.commit()
        while True:
            with self.sessions() as db:
                upload_id=db.scalar(select(KnowledgeUpload.id).where(KnowledgeUpload.status=='queued').order_by(KnowledgeUpload.created_at).limit(1))
            if upload_id: await self.process(upload_id)
            else: await asyncio.sleep(1)
