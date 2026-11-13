"""Проверки поиска и целостности ссылок без обращения к модели."""
import json
from pathlib import Path
from psb_engine import KnowledgeBase, validate

kb = KnowledgeBase.from_path(Path("psb_data/knowledge-base"))
assert len(kb.documents) == 21
cases = [
    ("Какая арендная плата Северный Склад?", "Договор аренды"),
    ("Максимальный срок испытания главному бухгалтеру?", "ТК ст70"),
    ("Срок оплаты П-17/2024 после дополнительного соглашения", "Доп соглашение"),
    ("Порядок согласования договора в 2023 году", "ред 2023"),
]
for query, title in cases:
    found = kb.search(query)
    assert any(title in f.title for f in found), query
f = kb.fragments[0]
valid = {"status":"answer", "answer":f"Положение подтверждено [{f.id}]", "evidence":[{"id":f.id,"quote":f.text[:80]}]}
assert validate(json.dumps(valid), [f])["sources"][0]["document_id"] == f.document_id
assert f.id in validate(json.dumps(dict(valid, answer="Положение подтверждено")), [f])["answer"]
for change in [dict(valid, evidence=[]), dict(valid, evidence=[{"id":f.id,"quote":"Такой цитаты в документе нет"}]), dict(valid, answer="Поддельный источник [unknown]")]:
    try:
        validate(json.dumps(change), [f])
        raise AssertionError("Пропущено неподтверждённое утверждение")
    except ValueError:
        pass
print(f"OK: {len(kb.documents)} documents, {len(kb.fragments)} fragments; retrieval, amendments, citations")
