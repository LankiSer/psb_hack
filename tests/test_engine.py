import asyncio
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from psb_engine import KnowledgeBase, checked_answer, prompt, split_dialogue, validate, answer_question, qualify_missing_references


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.kb = KnowledgeBase([
            ("документы компании__Договор Р-44-2022 Лира.txt", 'ДОГОВОР № Р-44/2022\nООО «Лира»\n1. Оплата в течение 20 дней.\n2. Гарантия 12 месяцев.'),
            ("документы компании__Доп соглашение Р-44-2022.txt", 'Дополнительное соглашение к договору № Р-44/2022\nС 01.02.2023 оплата в течение 40 дней.'),
            ("документы компании__Договор Р-55-2022 Лира-Сервис.txt", 'ДОГОВОР № Р-55/2022\nООО «Лира-Сервис»\nГарантию устанавливает изготовитель.'),
        ])

    def test_generic_amendment_not_demo_contract(self):
        sources = self.kb.search('Какой срок оплаты по договору Р-44/2022?')
        self.assertTrue(any('Доп соглашение' in f.title for f in sources))

    def test_entire_small_document_in_context(self):
        sources = self.kb.search('Р-44/2022 оплата')
        self.assertTrue(any('20 дней' in f.text and '12 месяцев' in f.text for f in sources))

    def test_corrected_party_in_last_user_turn(self):
        q = 'Пользователь: Лира, какая гарантия?\nАссистент: Лира или Лира-Сервис?\nПользователь: Лира-Сервис.'
        found = self.kb.search(q)
        self.assertIn('Лира-Сервис', found[0].title)
        self.assertFalse(any('20 дней' in f.text for f in found))

    def test_json_and_text_history(self):
        history, last = split_dialogue('Пользователь: Первый вопрос\nАссистент: Уточните\nПользователь: Второй вопрос')
        self.assertEqual(last, 'Второй вопрос')
        self.assertEqual(len(history), 2)
        self.assertEqual(split_dialogue(json.dumps([{'role':'user','content':'Первый'},{'role':'user','content':'Последний'}]))[1], 'Последний')

    def test_new_party_overrides_old_contract_number(self):
        found=self.kb.search('Пользователь: Оплата по Р-44/2022?\nАссистент: 20 дней.\nПользователь: Нет, я про Лира-Сервис, какая гарантия?')
        self.assertIn('Лира-Сервис',found[0].title)
        self.assertFalse(any('20 дней' in f.text for f in found))

    def test_explicit_short_article_number_and_code(self):
        kb=KnowledgeBase([
            ('законы__ТК_ст81.txt','Статья 81. ТК РФ\nОснования прекращения договора.'),
            ('законы__НК_ст81.txt','Статья 81. НК РФ\nУточненная налоговая декларация.'),
            ('законы__ТК_ст80.txt','Статья 80. ТК РФ\nПрекращение договора по инициативе работника.')])
        self.assertIn('НК',kb.search('Что устанавливает статья 81 НК?')[0].title)
        self.assertIn('81',kb.search('Что устанавливает статья 81 ТК?')[0].title)

    def test_tax_abbreviation_retrieves_expanded_name(self):
        kb=KnowledgeBase([('законы__Норма.txt','Налог на добавленную стоимость исчисляется по установленной ставке.')])
        self.assertTrue(kb.search('НДС'))

    def test_medium_article_keeps_exception(self):
        body='Статья 42.\nОбщее правило.\n'+('Дополнительное условие.\n'*90)+'Исключение: правило не применяется к указанной категории.'
        kb=KnowledgeBase([('законы__ТК_ст42.txt',body)])
        self.assertTrue(any('Общее правило' in f.text and 'Исключение' in f.text for f in kb.search('статья 42 ТК')))

    def test_inflected_company_name(self):
        kb=KnowledgeBase([
            ('документы компании__Договор.txt','Договор\nООО «Зелёный Берег»\nПредоставляет доступ круглосуточно.'),
            ('законы__Доступ.txt','Ночной доступ, правила доступа ночью.')])
        self.assertIn('Зелёный Берег',kb.search('Ночью доступ по договору с Зелёным Берегом?')[0].text)

    def test_context_has_bounded_size(self):
        kb=KnowledgeBase([(f'законы__Закон{i}.txt',f'Правило {i}.\n'+('Налоги и платежи.\n'*650)) for i in range(15)])
        self.assertLessEqual(sum(len(f.text) for f in kb.search('Налоги и платежи')),30000)

    def test_distant_parent_rule_is_kept_with_list_item(self):
        body='Статья 41.\n1. Первая норма.\n2. Льгота применяется при условии регистрации:\n'
        body+='1) категория первая;\n'+('Заполнитель без ключевых слов.\n'*400)
        body+='2) уникальные лабораторные приборы;\n3. Другая норма.'
        kb=KnowledgeBase([('законы__НК_ст41.txt',body)])
        sources=kb.search('Уникальные лабораторные приборы')
        self.assertTrue(any('Льгота применяется при условии регистрации' in f.text for f in sources))
        for f in sources:
            self.assertIn(f.text,body)
            if f.id.endswith('section'):
                self.assertEqual(f.text,'\n'.join(body.splitlines()[f.line_start-1:f.line_end]))

    def test_passage_never_inherits_previous_clause_rate(self):
        body='1. Первая ставка 1 процент.\n'+('Список первой категории.\n'*300)
        body+='2. Вторая ставка 8 процентов.\n'+('Особые приборы второй категории.\n'*300)
        kb=KnowledgeBase([('законы__НК_ст42.txt',body)])
        matches=[f for f in kb.fragments if 'Особые приборы' in f.text]
        self.assertTrue(matches)
        self.assertTrue(all(f.heading=='2. Вторая ставка 8 процентов.' for f in matches))
        f=next(f for f in matches if f.heading not in f.text)
        result=validate(json.dumps({'status':'answer','answer':'Условие [S1]','evidence':[{'id':'S1','quote':f.heading}]}),[f])
        source=result['sources'][0]
        self.assertEqual(source['line_start'],f.heading_line)
        self.assertEqual(body.splitlines()[source['line_start']-1],source['quote'])

    def test_short_answer_gets_only_verified_explanation(self):
        kb=KnowledgeBase([('документы компании__Условие.txt','Срок составляет 17 дней с даты передачи.')])
        result=validate(json.dumps({'status':'answer','answer':'17 дней [S1]','evidence':[]}),kb.fragments)
        self.assertIn('Основание: «Срок составляет 17 дней с даты передачи.»',result['answer'])

    def test_missing_referenced_articles_are_disclosed(self):
        kb=KnowledgeBase([('законы__АК_ст31.txt','Статья 31. Правило со ссылкой на статьи 77, 78 и 79.')])
        result=validate(json.dumps({'status':'answer','answer':'Условия определяют статьи 77, 78 и 79. [S1]','evidence':[]}),kb.fragments)
        result=qualify_missing_references(result,kb.catalog)
        self.assertIn('тексты статей 77, 78, 79',result['answer'])

    def test_existing_article_not_described_as_missing(self):
        kb=KnowledgeBase([('законы__АК_ст31.txt','Статья 31. Отсылка к статье 77.'),('законы__АК_ст77.txt','Статья 77. Условия.')])
        result=validate(json.dumps({'status':'answer','answer':'См. статью 77. [S1]','evidence':[]}),kb.fragments[:1])
        result=qualify_missing_references(result,kb.catalog)
        self.assertNotIn('Ограничение базы',result['answer'])

    def test_reference_to_different_code_is_not_mislabelled(self):
        kb=KnowledgeBase([('законы__НК_ст31.txt','Статья 31. Отсылка к статье 77 ГК РФ.')])
        result=validate(json.dumps({'status':'answer','answer':'Отсылка к статье 77 ГК РФ. [S1]','evidence':[]}),kb.fragments)
        self.assertNotIn('Ограничение базы',qualify_missing_references(result,kb.catalog)['answer'])

    def test_failed_planner_preserves_answer(self):
        async def planner(value): raise TimeoutError('fixture')
        async def generate(value): return json.dumps({'status':'answer','answer':'Условие [S1]','evidence':[]})
        result=asyncio.run(answer_question(self.kb,'Лира гарантия',[],generate,planner))
        self.assertEqual(result['status'],'answer')

    def test_planner_uses_only_existing_documents(self):
        async def planner(value):
            return json.dumps({'queries':['гарантия изготовителя'],'documents':['D9999']})
        async def generate(value):
            payload=json.loads(value)
            self.assertTrue(any('Гарантию устанавливает' in f['text'] for f in payload['sources']))
            self.assertNotIn('D9999',value)
            return json.dumps({'status':'answer','answer':'Условие [S1]','evidence':[]})
        asyncio.run(answer_question(self.kb,'Как устроено обслуживание?',[],generate,planner))

    def test_valid_answer_not_regenerated(self):
        calls=[]
        async def generate(p):
            calls.append(p)
            return json.dumps({'status':'answer','answer':'Условие [S1]','evidence':[]})
        result=asyncio.run(checked_answer('Условие',[],self.kb.fragments[:1],generate))
        self.assertEqual(len(calls),1)
        self.assertEqual(result['sources'][0]['document_id'],self.kb.fragments[0].document_id)

    def test_invalid_quote_repaired_not_silently_trusted(self):
        calls=[]
        async def generate(p):
            calls.append(p)
            evidence=[{'id':'S1','quote':'Выдуманная цитата'}] if len(calls)==1 else [{'id':'S1'}]
            return json.dumps({'status':'answer','answer':'Условие [S1]','evidence':evidence})
        result=asyncio.run(checked_answer('Условие',[],self.kb.fragments[:1],generate))
        self.assertEqual(len(calls),2)
        self.assertNotIn('Выдуманная',result['sources'][0]['quote'])

    def test_unknown_source_still_rejected(self):
        with self.assertRaises(ValueError):
            validate(json.dumps({'status':'answer','answer':'Факт [S999]','evidence':[]}),self.kb.fragments)

    def test_clarification_needs_no_fabricated_source(self):
        result=validate(json.dumps({'status':'clarification','answer':'Уточните договор.','evidence':[]}),self.kb.fragments)
        self.assertEqual(result['sources'],[])

    def test_refusal_without_sources_cannot_invent_a_law(self):
        result=validate(json.dumps({'status':'insufficient','answer':'Нет данных. Обратитесь к несуществующему закону № 999-ФЗ.','evidence':[]}),self.kb.fragments)
        self.assertNotIn('999',result['answer'])
        self.assertEqual(result['status'],'insufficient')
        self.assertEqual(result['sources'],[])

    def test_frontend_contract(self):
        result=validate(json.dumps({'status':'answer','answer':'Факт [S1]','evidence':[{'id':'S1'}]}),self.kb.fragments)
        self.assertEqual(set(result),{'answer','status','sources'})
        self.assertTrue({'id','document_id','title','quote','line_start','line_end'} <= set(result['sources'][0]))
        self.assertIn('['+result['sources'][0]['id']+']',result['answer'])

    def test_model_sees_one_unambiguous_source_id(self):
        payload=json.loads(prompt('Вопрос',[],self.kb.fragments))
        self.assertEqual(payload['sources'][0]['id'],'S1')
        self.assertNotIn('document_id',payload['sources'][0])
        self.assertNotIn(self.kb.fragments[0].document_id,json.dumps(payload))

    def test_grouped_citations(self):
        result=validate(json.dumps({'status':'answer','answer':'Сопоставлены [S1, S2]','evidence':[]}),self.kb.fragments)
        self.assertEqual(len(result['sources']),2)

    def test_clause_highlight_uses_real_line(self):
        kb=KnowledgeBase([('документы компании__Порядок.txt','Порядок\n1.1. Первый пункт.\n1.2. Второй пункт.')])
        result=validate(json.dumps({'status':'answer','answer':'Согласно п. 1.2 [S1]','evidence':[]}),kb.fragments)
        self.assertEqual(result['sources'][0]['quote'],'1.2. Второй пункт.')
        self.assertEqual(result['sources'][0]['line_start'],3)

if __name__=='__main__': unittest.main()
