"""Интеграция API и UI-контракт без настоящего вызова модели/БД."""
import json
from types import SimpleNamespace
from fastapi.testclient import TestClient
from app.main import app
from app.api.psb_deps import get_current_user,get_ollama

class FakeOllama:
    async def chat(self,system,prompt,**kwargs):
        payload,_=json.JSONDecoder().raw_decode(prompt)
        assert payload['question']=='А гарантия?'
        assert payload['history'][-1]['text']=='Договор с Альфа-Трейдинг'
        if 'sources' not in payload:
            return json.dumps({'queries':['гарантия изготовителя'],'documents':[]})
        source=payload['sources'][0]
        assert 'Альфа-Трейдинг' in source['title']
        return json.dumps({'status':'answer','answer':'Положение ['+source['id']+']','evidence':[{'id':source['id']}]})

client=TestClient(app)
assert client.get('/api/knowledge/documents').status_code==401
app.dependency_overrides[get_current_user]=lambda:SimpleNamespace(id=1)
app.dependency_overrides[get_ollama]=lambda:FakeOllama()
try:
    documents=client.get('/api/knowledge/documents').json()
    assert len(documents)==21
    r=client.post('/api/knowledge/ask',json={'question':'А гарантия?','history':[{'role':'user','text':'Договор с Альфа-Трейдинг'}]})
    assert r.status_code==200,r.text
    result=r.json();source=result['sources'][0]
    assert source['id'] in result['answer']
    doc=client.get('/api/knowledge/documents/'+source['document_id']).json()
    assert source['quote'] in doc['text']
    assert 1<=source['line_start']<=source['line_end']<=doc['line_count']
    assert client.get('/api/projects').status_code==404
    print('API: auth, history, citations, source preview and UI payload OK (mock model).')
finally:app.dependency_overrides.clear()
