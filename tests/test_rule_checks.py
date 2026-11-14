import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from rule_checks import upper_limit_risks, asserts, invalid_dates
from psb_engine import KnowledgeBase, review_issues


class RuleChecksTests(unittest.TestCase):
    def test_contract_year_is_not_duration(self):
        self.assertEqual(upper_limit_risks('Можно взять договор А-08/2024 на 2 рабочих дня?',
            ['Выдаётся не более 3 рабочих дней.']), [])

    def test_words_and_digits_have_same_boundary(self):
        for requested in ['4', 'четыре', 'четырёх']:
            for limit in ['3', 'трёх', '3 (трёх)']:
                with self.subTest(requested=requested, limit=limit):
                    self.assertTrue(upper_limit_risks(f'Можно на {requested} рабочих дня?',
                        [f'Срок не более {limit} рабочих дней.']))
        self.assertFalse(upper_limit_risks('Можно на три рабочих дня?', ['Не более 3 рабочих дней.']))

    def test_units_cannot_be_mixed(self):
        for requested in ['4 календарных дня', '4 дня', '400 рублей', '2024 года']:
            with self.subTest(requested=requested):
                self.assertFalse(upper_limit_risks(f'Можно на {requested}?', ['Не более 3 рабочих дней.']))

    def test_multiple_limits_require_scope_not_minimum(self):
        self.assertFalse(upper_limit_risks('Можно на 4 рабочих дня?',
            ['Обычно не более 3 рабочих дней. С разрешением не более 5 рабочих дней.']))

    def test_money_words_and_grouped_numbers(self):
        self.assertTrue(upper_limit_risks('Можно взять двенадцать миллионов рублей?',
            ['Не более 10 000 000 рублей.']))
        self.assertTrue(upper_limit_risks('Можно 12 млн рублей?', ['Не более десяти миллионов рублей.']))

    def test_approval_threshold_is_not_prohibition(self):
        self.assertFalse(upper_limit_risks('Можно заключить на 12 млн рублей?',
            ['Свыше 10 млн рублей требуется согласование.']))

    def test_negation_does_not_assert_immediate_destruction(self):
        pattern=r'(?:немедленно|сразу)\s+(?:удал|уничтож)'
        self.assertFalse(asserts(pattern, 'Нет, не нужно сразу удалить все данные.'))
        self.assertTrue(asserts(pattern, 'Нужно сразу удалить все данные.'))
        self.assertTrue(asserts(pattern, 'Нет сведений о хранении. Нужно сразу удалить данные.'))

    def test_impossible_dates_and_leap_year(self):
        self.assertEqual(invalid_dates('31.02.2025 и 29.02.2023, но 29.02.2024'),
            ['31.02.2025', '29.02.2023'])

    def test_review_does_not_flag_negated_obligation(self):
        kb=KnowledgeBase([('Правило.txt', 'Право на обработку зависит от основания.')])
        f=kb.fragments[0]
        result={'status':'answer', 'answer':'Нет, не нужно сразу удалить все данные.',
                'sources':[{'document_id':f.document_id,'title':f.title,'text':f.text}]}
        self.assertFalse(review_issues(result,kb.fragments,'Нужно сразу удалить данные?'))
