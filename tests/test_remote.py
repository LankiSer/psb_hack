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
