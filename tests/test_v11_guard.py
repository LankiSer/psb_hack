import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'backend'))
spec=importlib.util.spec_from_file_location('v11_engine',ROOT/'experiments/v11/psb_engine.py')
engine=importlib.util.module_from_spec(spec);sys.modules[spec.name]=engine;spec.loader.exec_module(engine)


class V11GuardTests(unittest.TestCase):
    def answer(self,question,source,draft,fail_review=False):
        kb=engine.KnowledgeBase([('Условия.txt',source)])
        calls=[]
        async def generate(p):
            calls.append(p)
            if fail_review and len(calls)>1:raise TimeoutError()
            return json.dumps({'status':'answer','answer':draft+' [S1]','evidence':[]})
        return asyncio.run(engine.checked_answer(question,[],kb.fragments,generate))

    def test_repeated_yes_above_limit_is_not_returned(self):
        result=self.answer('Можно взять оригинал на четыре рабочих дня?',
            'Оригиналы выдаются на срок не более 3 рабочих дней.',
            'Да, оригиналы выдаются на срок не более 3 рабочих дней.')
        self.assertFalse(result['answer'].startswith('Да'))
        self.assertIn('не более 3 рабочих дней',result['answer'])

    def test_question_number_cannot_justify_false_assertion(self):
        result=self.answer('Почему плата 500 000 рублей?',
            'Плата составляет 450 000 рублей в месяц.',
            'Плата составляет 500 000 рублей в месяц, возможно, в документе опечатка.')
        self.assertNotIn('500 000',result['answer'])
        self.assertNotIn('опечатка',result['answer'])
        self.assertIn('450 000',result['answer'])

    def test_valid_refutation_is_preserved(self):
        result=self.answer('Почему плата 500 000 рублей?',
            'Плата составляет 450 000 рублей в месяц.',
            'Плата не составляет 500 000 рублей: по документу она составляет 450 000 рублей.')
        self.assertIn('не составляет 500 000',result['answer'])

    def test_unknown_warranty_is_not_invented_after_failed_review(self):
        result=self.answer('Какая гарантия?',
            'Гарантия определяется производителем и указывается в талоне.',
            'Гарантия составляет 1 год.',fail_review=True)
        self.assertNotIn('1 год',result['answer'])
        self.assertIn('производителем',result['answer'])

    def test_different_units_do_not_remove_valid_yes(self):
        result=self.answer('Можно получить 4 рубля?',
            'Выплата 4 рубля производится в срок не более 3 рабочих дней.',
            'Да, выплата составляет 4 рубля.')
        self.assertTrue(result['answer'].startswith('Да'))
