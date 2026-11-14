"""Регрессия: обрезанное рассуждение не передаётся JSON-парсеру как готовый ответ."""
import asyncio
import json
import httpx
from app.config import Settings
from app.shared.ollama.client import OllamaClient, IncompleteAnswerError


async def main():
    for result in [
        {'done_reason':'length','message':{'content':'{"answer":'}},
        {'done_reason':'stop','message':{'content':'','thinking':'not a final answer'}},
        {'done_reason':'stop','message':{'content':'{"answer":"Готово"}'}}
    ]:
        def handle(request):
            payload=json.loads(request.content)
            assert payload['think'] is False
            assert payload['options']['num_ctx']==16384
            assert payload['options']['num_predict']==1600
            return httpx.Response(200,json=result)
        client=OllamaClient(Settings())
        client._client=lambda **kwargs:httpx.AsyncClient(transport=httpx.MockTransport(handle))
        try:
            text=await client.chat('system','question',max_tokens=1600,schema={'type':'object'},num_ctx=16384)
            assert text=='{"answer":"Готово"}'
            assert result['done_reason']=='stop' and result['message']['content']
        except IncompleteAnswerError:
            assert result['done_reason']=='length' or not result['message']['content']
    print('PASS: bounded non-thinking generation, context size, incomplete output handling')


if __name__=='__main__':asyncio.run(main())
