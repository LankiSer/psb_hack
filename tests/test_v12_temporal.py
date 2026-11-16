import asyncio
from datetime import date
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
spec=importlib.util.spec_from_file_location('v12_engine',ROOT/'experiments/v12/psb_engine.py')
engine=importlib.util.module_from_spec(spec);sys.modules[spec.name]=engine;spec.loader.exec_module(engine)


class TemporalTests(unittest.TestCase):
    def kb(self):
        return engine.KnowledgeBase([
            ('Регламент закупок ред 2021.txt','Редакция утратила силу с 15.04.2025.\nЛимит одобрения 8 миллионов рублей.'),
            ('Регламент закупок ред 2025.txt','Действует с 15.04.2025.\nЛимит одобрения 19 миллионов рублей.'),
            ('Регламент архива ред 2024.txt','Действует с 01.01.2024.\nВыдача на 7 дней.')])

    def test_month_is_interval_including_leap_day(self):
        self.assertEqual(engine.event_interval('Лимит в феврале 2024?'),(date(2024,2,1),date(2024,2,29)))

    def test_contract_number_is_not_event_date(self):
        self.assertIsNone(engine.event_interval('Оплата по А-12/2024?'))

    def test_two_dates_are_not_guessed(self):
        self.assertIsNone(engine.event_interval('Сравни 01.01.2024 и 01.01.2025'))
        self.assertIsNone(engine.event_interval('После 01.01.2025?'))

    def test_future_edition_is_removed_without_touching_other_family(self):
        kb=self.kb();found,meta=engine.edition_context(kb,'Лимит в марте 2025?',kb.fragments)
        self.assertTrue(any('8 миллионов' in f.text for f in found))
        self.assertFalse(any('19 миллионов' in f.text for f in found))
        self.assertTrue(any('7 дней' in f.text for f in found))
        self.assertTrue(any(item['excluded'] for item in meta['editions']))

    def test_exact_switch_date_uses_new_edition(self):
        kb=self.kb();found,_=engine.edition_context(kb,'Лимит на 15.04.2025?',kb.fragments)
        self.assertFalse(any('8 миллионов' in f.text for f in found))
        self.assertTrue(any('19 миллионов' in f.text for f in found))

    def test_month_crossing_change_keeps_both(self):
        kb=self.kb();found,_=engine.edition_context(kb,'Лимит в апреле 2025?',kb.fragments)
        self.assertTrue(any('8 миллионов' in f.text for f in found))
        self.assertTrue(any('19 миллионов' in f.text for f in found))

    def test_explicit_comparison_keeps_both(self):
        kb=self.kb();found,_=engine.edition_context(kb,'Сравни редакции в марте 2025',kb.fragments)
        self.assertTrue(any('19 миллионов' in f.text for f in found))

    def test_approval_date_does_not_become_effective_date(self):
        kb=engine.KnowledgeBase([('Положение ред 2022.txt','Лимит 8 рублей.'),
            ('Положение ред 2025.txt','Утверждено 15.04.2025. Лимит 19 рублей.')])
        found,meta=engine.edition_context(kb,'Лимит в 2024 году?',kb.fragments)
        self.assertEqual(found,kb.fragments)
        self.assertIsNone(meta)

    def test_retroactive_clause_prevents_hard_exclusion(self):
        kb=engine.KnowledgeBase([('Положение ред 2022.txt','Лимит 8 рублей.'),
            ('Положение ред 2025.txt','Действует с 15.04.2025. Распространяется на отношения, возникшие ранее. Лимит 19 рублей.')])
        found,_=engine.edition_context(kb,'Лимит в 2024 году?',kb.fragments)
        self.assertEqual(found,kb.fragments)

    def test_real_generation_context_excludes_future_rule(self):
        kb=self.kb();calls=[]
        async def generate(value):
            data=json.loads(value);calls.append(data)
            self.assertNotIn('19 миллионов',str(data['sources']))
            self.assertEqual(data['temporal_context']['event_from'],'2024-08-01')
            return json.dumps({'status':'answer','answer':'Условия определены прежней редакцией [S1]','evidence':[]})
        asyncio.run(engine.answer_question(kb,'Лимит в августе 2024 года?',[],generate))
        self.assertEqual(len(calls),1)
