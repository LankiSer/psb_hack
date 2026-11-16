import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
spec=importlib.util.spec_from_file_location('v10_engine',ROOT/'experiments/v10/psb_engine.py')
engine=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=engine
spec.loader.exec_module(engine)


class EvidenceTests(unittest.TestCase):
    def issues(self,answer,source,question='Каковы условия?'):
        return engine.quantity_support_issues(answer,[{'text':source}],question)

    def test_invented_warranty_is_detected(self):
        self.assertTrue(self.issues('Гарантия 36 месяцев.','Гарантия 24 месяца.'))

    def test_working_days_cannot_become_calendar_days(self):
        self.assertTrue(self.issues('Срок 5 календарных дней.','Срок 5 рабочих дней.'))
        self.assertFalse(self.issues('Срок 5 дней.','Срок 5 рабочих дней.'))

    def test_words_match_digits(self):
        self.assertFalse(self.issues('Срок двадцать четыре месяца.','Срок 24 месяца.'))

    def test_wrong_percentage_is_detected(self):
        self.assertTrue(self.issues('Штраф 2,5%.','Штраф 0,5%.'))

    def test_correct_percentage_is_not_flagged(self):
        self.assertFalse(self.issues('Штраф 0,5%.','Штраф 0,5 процента.'))

    def test_false_premise_can_be_repeated_and_refuted(self):
        self.assertFalse(self.issues('Не 36 месяцев, а 24 месяца.','Гарантия 24 месяца.',
                                     'Почему гарантия 36 месяцев?'))

    def test_no_extra_call_for_supported_answer(self):
        kb=engine.KnowledgeBase([('Условие.txt','Гарантия 24 месяца.')])
        calls=[]
        async def generate(p):
            calls.append(p)
            return json.dumps({'status':'answer','answer':'Гарантия 24 месяца [S1]','evidence':[]})
        result=asyncio.run(engine.checked_answer('Гарантия?',[],kb.fragments,generate))
        self.assertEqual(len(calls),1)
        self.assertEqual(result['status'],'answer')

    def test_review_corrects_invented_warranty(self):
        kb=engine.KnowledgeBase([('Условие.txt','Гарантия 24 месяца.')])
        calls=[]
        async def generate(p):
            calls.append(p)
            duration=36 if len(calls)==1 else 24
            return json.dumps({'status':'answer','answer':f'Гарантия {duration} месяца [S1]','evidence':[]})
        result=asyncio.run(engine.checked_answer('Гарантия?',[],kb.fragments,generate))
        self.assertEqual(len(calls),2)
        self.assertNotIn('36 месяца',result['answer'])

    def test_fast_mode_still_skips_semantic_review(self):
        kb=engine.KnowledgeBase([('Условие.txt','Гарантия 24 месяца.')])
        calls=[]
        async def generate(p):
            calls.append(p)
            return json.dumps({'status':'answer','answer':'Гарантия 36 месяцев [S1]','evidence':[]})
        asyncio.run(engine.checked_answer('Гарантия?',[],kb.fragments,generate,allow_review=False))
        self.assertEqual(len(calls),1)

    def test_dated_question_checks_multiple_editions(self):
        kb=engine.KnowledgeBase([
            ('Регламент ред 2022.txt','Действует с 01.01.2022. Лимит 8 миллионов рублей.'),
            ('Регламент ред 2025.txt','Действует с 01.01.2025. Лимит 15 миллионов рублей.')])
        calls=[]
        async def generate(p):
            calls.append(p)
            return json.dumps({'status':'answer','answer':'Применяется прежняя редакция. [S1]','evidence':[]})
        asyncio.run(engine.checked_answer('Какой лимит в августе 2024 года?',[],kb.fragments,generate))
        self.assertEqual(len(calls),2)
        self.assertIn('проверь редакцию на дату события',calls[-1])

    def test_failed_review_keeps_source_not_invented_number(self):
        kb=engine.KnowledgeBase([('Условие.txt','Гарантия устанавливается производителем.')])
        calls=[]
        async def generate(p):
            calls.append(p)
            if len(calls)>1:raise TimeoutError()
            return json.dumps({'status':'answer','answer':'Гарантия 1 год [S1]','evidence':[]})
        result=asyncio.run(engine.checked_answer('На сколько гарантия?',[],kb.fragments,generate))
        self.assertNotIn('1 год',result['answer'])
        self.assertIn('Гарантия устанавливается производителем.',result['answer'])

    def test_repeated_hallucination_is_not_returned(self):
        kb=engine.KnowledgeBase([('Условие.txt','Гарантия 24 месяца.')])
        async def generate(p):
            return json.dumps({'status':'answer','answer':'Гарантия 36 месяцев [S1]','evidence':[]})
        result=asyncio.run(engine.checked_answer('Гарантия?',[],kb.fragments,generate))
        self.assertNotIn('36 месяцев',result['answer'])
        self.assertIn('24 месяца',result['answer'])
