"""Прямой прогон маршрута чата по учебному корпусу без сервера и учётных записей."""
import asyncio
import time
from types import SimpleNamespace

from app.api.routes.knowledge import ask, Question, knowledge
from app.config import Settings
from app.shared.ollama.client import OllamaClient


class Corpus:
    def make_knowledge(self, path, user):
        return knowledge()

    async def hints(self, user, question):
        return {}, ''


async def main():
    client=OllamaClient(Settings())
    for question in ['Какой срок оплаты по договору П-17/2024 после допсоглашения?',
                     'Какой срок оплаты по договору П-17/2024 после допсоглашения?']:
        started=time.monotonic()
        result=await ask(Question(question=question),client,SimpleNamespace(id=0),Corpus())
        assert result['status']=='answer' and result['sources'], result['status']
        assert any('соглашение' in s['title'].lower() for s in result['sources'])
        print(f"PASS: seconds={time.monotonic()-started:.1f}; sources={len(result['sources'])}; valid structured answer",flush=True)


if __name__=='__main__':asyncio.run(main())
