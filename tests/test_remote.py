import asyncio
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import httpx

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from psb_engine import generate_remote

class RemoteTests(unittest.TestCase):
    def run_transport(self, handle, model='deepseek-v4.1-flash', **kwargs):
        original=httpx.AsyncClient
        def client(**options): return original(transport=httpx.MockTransport(handle),**options)
        with patch.dict(os.environ,{'LLM_BASE_URL':'http://test.invalid/v1','LLM_API_KEY':'fixture-only','LLM_MODEL':model}),patch('psb_engine.httpx.AsyncClient',side_effect=client):
            return asyncio.run(generate_remote('fixture',**kwargs))

    def test_planner_disables_thinking(self):
        from psb_engine import PLANNER_SYSTEM
        def handle(request):
            data=json.loads(request.content)
            self.assertEqual(data['thinking'],{'type':'disabled'})
            self.assertEqual(data['max_tokens'],1000)
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{}'}}]})
        self.run_transport(handle,system=PLANNER_SYSTEM,max_tokens=1000)

    def test_provider_options_fallback_without_losing_answer(self):
        payloads=[]
        def handle(request):
            data=json.loads(request.content);payloads.append(data)
            if len(payloads)==1:
                self.assertEqual(data['reasoning_effort'],'low')
                return httpx.Response(422,json={'error':'unsupported parameter'})
            self.assertNotIn('thinking',data)
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'final','reasoning_content':'private'}}]})
        self.assertEqual(self.run_transport(handle),'final')
        self.assertEqual(len(payloads),2)

    def test_truncated_output_not_accepted_at_maximum_budget(self):
        def handle(request):
            return httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'partial'}}]})
        with self.assertRaisesRegex(ValueError,'лимит токенов'):
            self.run_transport(handle,max_tokens=16384)

    def test_platform_env_and_truncated_response_retry(self):
        payloads=[]
        def handle(request):
            self.assertEqual(str(request.url),'http://test.invalid/v1/chat/completions')
            self.assertEqual(request.headers['Authorization'],'Bearer fixture-only')
            data=json.loads(request.content);payloads.append(data)
            self.assertEqual(data['model'],'platform-provided-model')
            if len(payloads)==1:
                return httpx.Response(200,json={'choices':[{'finish_reason':'length','message':{'content':'{"answer":'}}]})
            return httpx.Response(200,json={'choices':[{'finish_reason':'stop','message':{'content':'{"status":"insufficient","answer":"Нет данных","evidence":[]}'}}]})
        original=httpx.AsyncClient
        def client(**kwargs): return original(transport=httpx.MockTransport(handle),**kwargs)
        with patch.dict(os.environ,{'LLM_BASE_URL':'http://test.invalid/v1','LLM_API_KEY':'fixture-only','LLM_MODEL':'platform-provided-model','MAX_TOKENS':'1024'}),patch('psb_engine.httpx.AsyncClient',side_effect=client):
            result=asyncio.run(generate_remote('fixture'))
        self.assertEqual(len(payloads),2)
        self.assertEqual(payloads[1]['max_tokens'],2048)
        self.assertEqual(json.loads(result)['status'],'insufficient')

if __name__=='__main__':unittest.main()
