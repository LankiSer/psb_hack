import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from psb_engine import KnowledgeBase, prompt


class RetrievalScopeTests(unittest.TestCase):
    def setUp(self):
        self.kb = KnowledgeBase([
            ('Договор А-11-2024.txt', 'Договор А-11/2024. ООО «Лира».\nОплата через 17 дней.'),
            ('Договор А-22-2025.txt', 'Договор А-22/2025. ООО «Лира».\nОплата через 29 дней.'),
            ('Договор Б-33-2025.txt', 'Договор Б-33/2025. ООО «Орион».\nОплата через 41 день.'),
            ('законы__Общее правило.txt', 'Оплата осуществляется по условиям договора.')])

    def test_party_does_not_arbitrarily_choose_one_of_two_contracts(self):
        found = self.kb.search('Когда оплата по договору с Лира?')
        self.assertTrue(any('17 дней' in f.text for f in found))
        self.assertTrue(any('29 дней' in f.text for f in found))
        self.assertFalse(any('41 день' in f.text for f in found))

    def test_latest_user_identifier_replaces_old_history(self):
        q = json.dumps([
            {'role':'user','text':'Договор А-11/2024'},
            {'role':'user','text':'Теперь договор А-22/2025'},
            {'role':'user','text':'Какой срок оплаты?'}],ensure_ascii=False)
        found = self.kb.search(q)
        self.assertTrue(any('29 дней' in f.text for f in found))
        self.assertFalse(any('17 дней' in f.text for f in found))

    def test_ranker_cannot_evict_explicit_contract(self):
        unrelated = next(f.id for f in self.kb.fragments if 'Общее правило' in f.title)
        found = self.kb.search('Оплата по А-11/2024?',limit=1,ranked_fragments=[unrelated])
        self.assertIn('17 дней',found[0].text)

    def test_long_explicit_contract_uses_relevant_clause_not_first_page(self):
        body='Договор К-45/2026. ООО «Вектор».\n1. Предмет.\n'+('Общие сведения.\n'*1000)
        body+='2. Гарантия.\nУникальный гарантийный срок составляет 27 месяцев.\n'+('Технические сведения.\n'*1000)
        kb=KnowledgeBase([('Договор К-45-2026.txt',body)])
        found=kb.search('Какой гарантийный срок по К-45/2026?',limit=1)
        self.assertTrue(any('27 месяцев' in f.text for f in found))

    def test_comparison_keeps_both_explicit_contracts(self):
        found=self.kb.search('Сравни оплату по А-11/2024 и А-22/2025')
        self.assertTrue(any('17 дней' in f.text for f in found))
        self.assertTrue(any('29 дней' in f.text for f in found))

    def test_ambiguous_party_keeps_options_even_with_one_ranked_hit(self):
        first = next(f.id for f in self.kb.fragments if '17 дней' in f.text)
        found=self.kb.search('Оплата по договору с Лира?',limit=1,ranked_fragments=[first])
        self.assertTrue(any('17 дней' in f.text for f in found))
        self.assertTrue(any('29 дней' in f.text for f in found))

    def test_nonexistent_identifier_does_not_substitute_other_contract(self):
        found=self.kb.search('Какой срок оплаты по А-99/2026?')
        self.assertFalse(any('17 дней' in f.text or '29 дней' in f.text or '41 день' in f.text for f in found))

    def test_current_party_overrides_previous_identifier(self):
        q=json.dumps([{'role':'user','text':'Договор А-11/2024'},
                      {'role':'user','text':'Теперь оплата по договору с Орион?'}],ensure_ascii=False)
        found=self.kb.search(q)
        self.assertTrue(any('41 день' in f.text for f in found))
        self.assertFalse(any('17 дней' in f.text for f in found))

    def test_answer_sees_only_catalog_of_retrieved_documents(self):
        source=next(f for f in self.kb.fragments if '17 дней' in f.text)
        data=json.loads(prompt('Оплата?',[],[source],self.kb.catalog))
        self.assertEqual(data['catalog'],[source.title])
        self.assertEqual(data['sources'][0]['text'],source.text)
