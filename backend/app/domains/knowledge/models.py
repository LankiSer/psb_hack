from datetime import datetime
from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.shared.db import Base


class KnowledgeUpload(Base):
    __tablename__ = 'knowledge_uploads'
    __table_args__ = (UniqueConstraint('owner_id', 'sha256'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, index=True)
    filename: Mapped[str] = mapped_column(String(240))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default='queued', index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(40), default='Документ')
    storage_name: Mapped[str] = mapped_column(String(300), default='')
    document_id: Mapped[str] = mapped_column(String(12), default='')
    text: Mapped[str] = mapped_column(Text, default='')
    error: Mapped[str] = mapped_column(String(500), default='')
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    def public(self):
        return {key:getattr(self,key) for key in ('id','filename','size','status','progress','kind','document_id','error','chunk_count','created_at')}
