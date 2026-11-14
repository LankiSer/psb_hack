import asyncio
import os
import unittest
from unittest.mock import patch
from pathlib import Path
import sys

import httpx

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from psb_engine import KnowledgeBase
from psb_retrieval import RemoteRetrieval


class SemanticTests(unittest.TestCase):
    def setUp(self):
        self.kb=KnowledgeBase([('Первый.txt','Аренда склада'),('Второй.txt','Поставка компьютеров')])

    def run_case(self, handler, action):
        original=httpx.AsyncClient
        def client(**kwargs):
            return original(transport=httpx.MockTransport(handler),**kwargs)
        with patch.dict(os.environ,{'EMB_MODEL':'fixture-model','LLM_BASE_URL':'http://fixture/v1','LLM_API_KEY':'fixture-key'}),patch('psb_retrieval.httpx.AsyncClient',side_effect=client):
            retrieval=RemoteRetrieval(self.kb)
            return asyncio.run(action(retrieval))

    def test_indices_restored_and_query_ranked(self):
        calls=[]
        def handle(request):
            calls.append(request)
            values=([{'index':1,'embedding':[0,1]},{'index':0,'embedding':[1,0]}] if len(calls)==1 else [{'index':0,'embedding':[0,1]}])
            return httpx.Response(200,json={'data':values})
        async def action(retrieval):
            self.assertTrue(await retrieval.prepare())
            hints=await retrieval.hints('Техника')
            self.assertEqual(hints['fragments'][0],self.kb.fragments[1].id)
        self.run_case(handle,action)

    def test_failed_service_keeps_lexical_available(self):
        async def action(retrieval):
            self.assertFalse(await retrieval.prepare())
            self.assertEqual(await retrieval.hints('Аренда'),{})
            self.assertTrue(self.kb.search('Аренда'))
        self.run_case(lambda request:httpx.Response(404),action)

    def test_partial_index_never_used(self):
        async def action(retrieval):
            self.assertFalse(await retrieval.prepare())
            self.assertEqual(retrieval.vectors,[])
        self.run_case(lambda request:httpx.Response(200,json={'data':[{'index':0,'embedding':[1,0]}]}),action)

    def test_nonfinite_embedding_rejected(self):
        for value in ([float('nan')],[0,0],[],['bad']):
            with self.assertRaises(ValueError):RemoteRetrieval.normalize(value)
