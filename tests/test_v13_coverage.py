import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
spec=importlib.util.spec_from_file_location('v13_engine',ROOT/'experiments/v13/psb_engine.py')
engine=importlib.util.module_from_spec(spec);sys.modules[spec.name]=engine;spec.loader.exec_module(engine)


class CoverageTests(unittest.TestCase):
    def setUp(self):
        self.kb=engine.KnowledgeBase([
            ('Договор Л-21-2022.txt','Договор Л-21/2022. ООО «Лира». Оплата через 17 дней после акта.'),
            ('Договор М-32-2023.txt','Договор М-32/2023. ООО «Маяк». Оплата через 39 дней после поставки.'),
            ('Доп соглашение М-32-2023.txt','К договору М-32/2023. Оплата изменена на 43 дня.'),
            ('Договор Ф-45-2024.txt','Договор Ф-45/2024. ООО «Фон». Оплата через 72 дня.')])

    def test_one_planner_selection_cannot_remove_second_contract(self):
        async def planner(value):
            data=json.loads(value)
            first=next(c['id'] for c in data['candidates'] if 'Л-21' in c['title'])
            return json.dumps({'queries':[],'documents':[],'fragments':[first]})
        async def generate(value):
            data=json.loads(value);text='\n'.join(s['text'] for s in data['sources'])
            self.assertIn('17 дней',text);self.assertIn('39 дней',text);self.assertIn('43 дня',text)
            self.assertNotIn('72 дня',text)
            return json.dumps({'status':'answer','answer':'Условия различаются [S1]','evidence':[]})
        asyncio.run(engine.answer_question(self.kb,'Сравни оплату Л-21/2022 и М-32/2023',[],generate,planner))

    def test_single_document_context_is_unchanged(self):
        found=self.kb.search('Оплата Л-21/2022?')
        self.assertEqual(engine.complete_comparison_sources(self.kb,'Оплата Л-21/2022?',found),found)

    def test_unknown_document_is_not_invented(self):
        found=engine.complete_comparison_sources(self.kb,'Сравни Л-21/2022 и Х-99/2028',[])
        self.assertTrue(found)
        self.assertFalse(any('М-32' in f.title for f in found))
        self.assertTrue(all(f.document_id in self.kb.documents for f in found))

    def test_context_is_bounded(self):
        found=engine.complete_comparison_sources(self.kb,'Сравни Л-21/2022 и М-32/2023',self.kb.fragments)
        self.assertLessEqual(sum(len(f.text) for f in found),30000)
