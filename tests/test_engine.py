import asyncio
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from psb_engine import KnowledgeBase, checked_answer, prompt, split_dialogue, validate, answer_question, qualify_missing_references, grounded_queries, review_issues, lexical_deadline_answer


class EngineTests(unittest.TestCase):
    def test_large_parent_sections_do_not_evict_other_answer_passages(self):
        words=['апельсин','самолет','корвет','монета','платина','янтарь','брусника','василек']
        docs=[]
        for word in words:
            docs.append((f'законы__Правило_{word}.txt','1. Условия применения нормы.\n'+('Общие пояснения без искомого предмета.\n'*320)+f'Особое требование: {word} разрешен при регистрации. '+('Действуют перечисленные ограничения. '*25)))
        kb=KnowledgeBase(docs)
        targets=[f.id for f in kb.fragments if 'разрешен при регистрации' in f.text]
        found=kb.search('Какие требования установлены для '+' '.join(words)+'?',ranked_fragments=targets)
        text='\n'.join(f.text for f in found)
        self.assertTrue(all(f'{word} разрешен при регистрации' in text for word in words))
        self.assertLessEqual(sum(len(f.text) for f in found),30000)

    def test_planner_does_not_invent_numbers_or_parties(self):
        values=grounded_queries(['архив срок 5 лет','выдача оригинала на 4 дня','договор ООО «Чужая компания»','выдача оригинала'],
            'Можно взять оригинал на 4 дня?',[])
        self.assertEqual(values,['выдача оригинала на 4 дня'])

    def test_planner_keeps_user_history_but_not_assistant_inventions(self):
        values=grounded_queries(['поставка Р-44/2022','оплата 999 дней'], 'А оплата?',
            [{'role':'user','text':'Договор Р-44/2022'},{'role':'assistant','text':'999 дней'}])
        self.assertEqual(values,['поставка Р-44/2022'])

    def test_targeted_review_adds_missing_amendment_citation(self):
        sources=self.kb.fragments
        contract=next(i+1 for i,f in enumerate(sources) if 'Р-44-2022 Лира' in f.title)
        amendment=next(i+1 for i,f in enumerate(sources) if 'Доп соглашение' in f.title)
        calls=[]
        async def generate(value):
            calls.append(value)
            answer=f'Дополнительное соглашение изменяет срок оплаты. [S{contract}]'
            if len(calls)>1:answer+=f' [S{amendment}]'
            return json.dumps({'status':'answer','answer':answer,'evidence':[]})
        result=asyncio.run(checked_answer('Оплата?',[],sources,generate))
        self.assertEqual(len(calls),2)
        self.assertEqual(len(result['sources']),2)

    def test_failed_review_preserves_verified_draft(self):
        calls=[]
        async def generate(value):
            calls.append(value)
            if len(calls)>1:raise TimeoutError()
            return json.dumps({'status':'answer','answer':'Дата 31.02.2025 [S1]','evidence':[]})
        result=asyncio.run(checked_answer('Дата?',[],self.kb.fragments,generate))
        self.assertEqual(len(calls),2)
        self.assertEqual(result['status'],'answer')

    def test_review_cannot_turn_supported_answer_into_refusal(self):
        calls=[]
        async def generate(value):
            calls.append(value)
            if len(calls)>1:return json.dumps({'status':'insufficient','answer':'Нет данных','evidence':[]})
            return json.dumps({'status':'answer','answer':'Дата 31.02.2025 [S1]','evidence':[]})
        result=asyncio.run(checked_answer('Дата?',[],self.kb.fragments,generate))
        self.assertEqual(result['status'],'answer')

    def test_categorical_question_checks_conditional_rule(self):
        kb=KnowledgeBase([('Условия.txt','Продление допускается при наличии разрешения. Отмена не описана.')])
        calls=[]
        async def generate(value):
            calls.append(value)
            text='Отмена допускается при наличии разрешения.' if len(calls)==1 else 'Условие разрешения относится к продлению; порядок отмены не описан.'
            return json.dumps({'status':'answer','answer':text+' [S1]','evidence':[]})
        result=asyncio.run(checked_answer('Значит, обязаны сразу отменить?',[],kb.fragments,generate))
        self.assertEqual(len(calls),2)
        self.assertIn('относится к продлению',result['answer'])

    def test_absence_of_conditions_is_not_disclosure_of_missing_articles(self):
        kb=KnowledgeBase([('законы__АК_ст31.txt','При наличии оснований статьи 32 допускается продление.')])
        result=validate(json.dumps({'status':'answer','answer':'При отсутствии оснований статьи 32 продление не допускается [S1]','evidence':[]}),kb.fragments)
        result=qualify_missing_references(result,kb.catalog)
        self.assertIn('Ограничение базы',result['answer'])

    def test_parenthetical_source_is_validated_and_resolved(self):
        source=self.kb.fragments[0]
        result=validate(json.dumps({'status':'answer','answer':'Условия описаны в документе (S1).','evidence':[]}),[source])
        self.assertIn('['+source.id+']',result['answer'])
        self.assertNotIn('(S1)',result['answer'])
        with self.assertRaises(ValueError):
            validate(json.dumps({'status':'answer','answer':'Условия (S99).','evidence':[]}),[source])

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

    def test_review_flags_echoed_question(self):
        q='Договор на 12 млн рублей заключали в августе 2024 года. Нужно ли было одобрение генерального директора?'
        result=validate(json.dumps({'status':'answer','answer':q+' [S1]','evidence':[]},ensure_ascii=False),self.kb.fragments)
        self.assertTrue(any('\u043f\u043e\u0432\u0442\u043e\u0440\u044f\u0435\u0442 \u0432\u043e\u043f\u0440\u043e\u0441' in issue for issue in review_issues(result,self.kb.fragments,q)))

    def test_review_flags_limit_exceedance_yes(self):
        kb=KnowledgeBase([('archive.txt','\u0412\u044b\u0434\u0430\u0447\u0430 \u043e\u0440\u0438\u0433\u0438\u043d\u0430\u043b\u043e\u0432 \u043f\u0440\u043e\u0438\u0437\u0432\u043e\u0434\u0438\u0442\u0441\u044f \u043f\u043e \u0437\u0430\u044f\u0432\u043a\u0435 \u043d\u0430 \u0441\u0440\u043e\u043a \u043d\u0435 \u0431\u043e\u043b\u0435\u0435 3 \u0440\u0430\u0431\u043e\u0447\u0438\u0445 \u0434\u043d\u0435\u0439.')])
        q='\u041c\u043e\u0436\u043d\u043e \u0432\u0437\u044f\u0442\u044c \u043e\u0440\u0438\u0433\u0438\u043d\u0430\u043b \u0438\u0437 \u0430\u0440\u0445\u0438\u0432\u0430 \u043d\u0430 4 \u0440\u0430\u0431\u043e\u0447\u0438\u0445 \u0434\u043d\u044f?'
        result=validate(json.dumps({'status':'answer','answer':'\u0414\u0430, \u0432\u044b\u0434\u0430\u0447\u0430 \u043f\u0440\u043e\u0438\u0437\u0432\u043e\u0434\u0438\u0442\u0441\u044f \u043f\u043e \u0437\u0430\u044f\u0432\u043a\u0435. [S1]','evidence':[]},ensure_ascii=False),kb.fragments)
        self.assertTrue(any('\u043f\u0440\u0435\u0432\u044b\u0448\u0430\u0435\u0442 \u043b\u0438\u043c\u0438\u0442' in issue for issue in review_issues(result,kb.fragments,q)))

    def test_review_does_not_flag_approval_threshold(self):
        kb=KnowledgeBase([('reg.txt','2.4. \u0414\u043e\u0433\u043e\u0432\u043e\u0440\u044b \u043d\u0430 \u0441\u0443\u043c\u043c\u0443 \u0441\u0432\u044b\u0448\u0435 10 000 000 \u0440\u0443\u0431\u043b\u0435\u0439 \u043f\u043e\u0434\u043b\u0435\u0436\u0430\u0442 \u043e\u0434\u043e\u0431\u0440\u0435\u043d\u0438\u044e \u0433\u0435\u043d\u0435\u0440\u0430\u043b\u044c\u043d\u044b\u043c \u0434\u0438\u0440\u0435\u043a\u0442\u043e\u0440\u043e\u043c.')])
        q='\u0414\u043e\u0433\u043e\u0432\u043e\u0440 \u043d\u0430 12 \u043c\u043b\u043d \u0440\u0443\u0431\u043b\u0435\u0439 \u0437\u0430\u043a\u043b\u044e\u0447\u0430\u043b\u0438 \u0432 \u0430\u0432\u0433\u0443\u0441\u0442\u0435 2024 \u0433\u043e\u0434\u0430. \u041d\u0443\u0436\u043d\u043e \u043b\u0438 \u0431\u044b\u043b\u043e \u043e\u0434\u043e\u0431\u0440\u0435\u043d\u0438\u0435 \u0433\u0435\u043d\u0435\u0440\u0430\u043b\u044c\u043d\u043e\u0433\u043e \u0434\u0438\u0440\u0435\u043a\u0442\u043e\u0440\u0430?'
        result=validate(json.dumps({'status':'answer','answer':'\u0414\u0430, \u0442\u0440\u0435\u0431\u043e\u0432\u0430\u043b\u043e\u0441\u044c \u043e\u0434\u043e\u0431\u0440\u0435\u043d\u0438\u0435 \u0433\u0435\u043d\u0435\u0440\u0430\u043b\u044c\u043d\u043e\u0433\u043e \u0434\u0438\u0440\u0435\u043a\u0442\u043e\u0440\u0430. [S1]','evidence':[]},ensure_ascii=False),kb.fragments)
        self.assertFalse(any('\u043f\u0440\u0435\u0432\u044b\u0448\u0430\u0435\u0442 \u043b\u0438\u043c\u0438\u0442' in issue for issue in review_issues(result,kb.fragments,q)))

    def test_review_flags_invented_notification_duty(self):
        kb=KnowledgeBase([('pdn.txt','\u0421\u043e\u0433\u043b\u0430\u0441\u0438\u0435 \u043c\u043e\u0436\u0435\u0442 \u0431\u044b\u0442\u044c \u043e\u0442\u043e\u0437\u0432\u0430\u043d\u043e. \u041e\u043f\u0435\u0440\u0430\u0442\u043e\u0440 \u0432\u043f\u0440\u0430\u0432\u0435 \u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0438\u0442\u044c \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u043a\u0443 \u043f\u0440\u0438 \u043d\u0430\u043b\u0438\u0447\u0438\u0438 \u043e\u0441\u043d\u043e\u0432\u0430\u043d\u0438\u0439.')])
        answer='\u041d\u0443\u0436\u043d\u043e \u0443\u0432\u0435\u0434\u043e\u043c\u0438\u0442\u044c \u0441\u0443\u0431\u044a\u0435\u043a\u0442\u0430 \u0438 \u0441\u0440\u0430\u0437\u0443 \u0443\u0434\u0430\u043b\u0438\u0442\u044c \u0434\u0430\u043d\u043d\u044b\u0435. [S1]'
        result=validate(json.dumps({'status':'answer','answer':answer,'evidence':[]},ensure_ascii=False),kb.fragments)
        issues=review_issues(result,kb.fragments,'\u041e\u0431\u044f\u0437\u0430\u043d\u044b \u043b\u0438 \u0441\u0440\u0430\u0437\u0443 \u0443\u0434\u0430\u043b\u0438\u0442\u044c \u0432\u0441\u0451 \u043f\u043e\u0441\u043b\u0435 \u043e\u0442\u0437\u044b\u0432\u0430 \u0441\u043e\u0433\u043b\u0430\u0441\u0438\u044f?')
        self.assertTrue(any('\u0443\u0432\u0435\u0434\u043e\u043c' in issue for issue in issues))

    def test_false_insufficient_triggers_review_to_answer(self):
        kb=KnowledgeBase([('contract PT-05.txt','4.2. \u041f\u0440\u0435\u0434\u043e\u043f\u043b\u0430\u0442\u0430 \u0434\u043e\u043f\u0443\u0441\u043a\u0430\u0435\u0442\u0441\u044f \u043f\u043e \u0441\u043e\u0433\u043b\u0430\u0448\u0435\u043d\u0438\u044e \u0441\u0442\u043e\u0440\u043e\u043d \u0438 \u0443\u043a\u0430\u0437\u044b\u0432\u0430\u0435\u0442\u0441\u044f \u0432 \u0441\u0447\u0451\u0442\u0435.')])
        calls=[]
        async def generate(value):
            calls.append(value)
            if len(calls)==1:
                return json.dumps({'status':'insufficient','answer':'Unclear contract.','evidence':[]})
            return json.dumps({'status':'answer','answer':'\u041f\u0440\u0435\u0434\u043e\u043f\u043b\u0430\u0442\u0430 \u0434\u043e\u043f\u0443\u0441\u043a\u0430\u0435\u0442\u0441\u044f \u043f\u043e \u043f. 4.2. [S1]','evidence':[]},ensure_ascii=False)
        result=asyncio.run(checked_answer('\u041f\u043e \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0443 \u0441 \u00ab\u0410\u043b\u044c\u0444\u0430-\u0422\u0440\u0435\u0439\u0434\u0438\u043d\u0433\u00bb \u043c\u043e\u0436\u0435\u043c \u043e\u043f\u043b\u0430\u0442\u0438\u0442\u044c \u0430\u0432\u0430\u043d\u0441\u043e\u043c?',[],kb.fragments,generate))
        self.assertEqual(len(calls),2)
        self.assertEqual(result['status'],'answer')
        self.assertIn('\u041f\u0440\u0435\u0434\u043e\u043f\u043b\u0430\u0442\u0430',result['answer'])

    def test_fast_mode_skips_review(self):
        calls=[]
        async def generate(value):
            calls.append(value)
            return json.dumps({'status':'answer','answer':'Дата 31.02.2025 [S1]','evidence':[]})
        result=asyncio.run(checked_answer('Дата?',[],self.kb.fragments,generate,allow_review=False))
        self.assertEqual(len(calls),1)
        self.assertEqual(result['status'],'answer')

    def test_fast_mode_skips_planner(self):
        calls=[]
        async def generate(value):
            calls.append(('gen',value))
            return json.dumps({'status':'answer','answer':'Факт [S1]','evidence':[]})
        async def planner(value):
            calls.append(('plan',value))
            return json.dumps({'queries':['x'],'documents':[]})
        result=asyncio.run(answer_question(self.kb,'Лира гарантия',[],generate,planner,allow_plan=False,allow_review=False))
        self.assertTrue(all(kind=='gen' for kind,_ in calls))
        self.assertEqual(result['status'],'answer')

    def test_lexical_deadline_answer_uses_fragments_not_random(self):
        result=lexical_deadline_answer(self.kb,'Оплата по договору Р-44/2022')
        self.assertEqual(result['status'],'answer')
        self.assertGreater(len(result['sources']),0)
        self.assertIn('20 дней',result['answer'])
        self.assertNotRegex(result['answer'],r'^(?:Да|Нет)\.?$')

    def test_clause_highlight_uses_real_line(self):
        kb=KnowledgeBase([('документы компании__Порядок.txt','Порядок\n1.1. Первый пункт.\n1.2. Второй пункт.')])
        result=validate(json.dumps({'status':'answer','answer':'Согласно п. 1.2 [S1]','evidence':[]}),kb.fragments)
        self.assertEqual(result['sources'][0]['quote'],'1.2. Второй пункт.')
        self.assertEqual(result['sources'][0]['line_start'],3)

if __name__=='__main__': unittest.main()
