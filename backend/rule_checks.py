"""Ограниченные проверки фактов: числа сравниваются только вместе с единицами."""
import re
from datetime import datetime
from decimal import Decimal

WORDS = {}
for value, variants in enumerate([
    'ноль нуля', 'один одна одно одного одной', 'два две двух', 'три трех', 'четыре четырех',
    'пять пяти', 'шесть шести', 'семь семи', 'восемь восьми', 'девять девяти', 'десять десяти',
    'одиннадцать одиннадцати', 'двенадцать двенадцати', 'тринадцать тринадцати',
    'четырнадцать четырнадцати', 'пятнадцать пятнадцати', 'шестнадцать шестнадцати',
    'семнадцать семнадцати', 'восемнадцать восемнадцати', 'девятнадцать девятнадцати']):
    for word in variants.split():WORDS[word]=value
for value, variants in [(20,'двадцать двадцати'),(30,'тридцать тридцати'),(40,'сорок сорока'),
                        (50,'пятьдесят пятидесяти'),(60,'шестьдесят шестидесяти'),
                        (70,'семьдесят семидесяти'),(80,'восемьдесят восьмидесяти'),
                        (90,'девяносто девяноста'),(100,'сто ста'),(200,'двести двухсот'),
                        (300,'триста трехсот'),(400,'четыреста четырехсот'),(500,'пятьсот пятисот'),
                        (600,'шестьсот шестисот'),(700,'семьсот семисот'),(800,'восемьсот восьмисот'),
                        (900,'девятьсот девятисот')]:
    for word in variants.split():WORDS[word]=value
SCALES={'тысяча':1000,'тысячи':1000,'тысяч':1000,'тысячу':1000,'тысячах':1000,
        'миллион':1000000,'миллиона':1000000,'миллионов':1000000,'млн':1000000}
WORD = '(?:'+'|'.join(sorted(WORDS.keys()|SCALES.keys(),key=len,reverse=True))+')'
NUMBER = rf'(?:\d+(?:[ \u00a0]\d{{3}})*(?:[.,]\d+)?(?:\s+(?:млн|миллион\w*|тысяч\w*))?|{WORD}(?:\s+{WORD})*)'
QUANTITY = re.compile(rf'(?<![\w/])(?P<number>{NUMBER})\s+(?:(?P<kind>рабоч\w*|календарн\w*)\s+)?(?P<unit>дн\w*|день|сут\w*|руб\w*|процент\w*|месяц\w*|лет|год\w*)\b',re.I)


def number(value):
    value=value.lower().replace('ё','е')
    if value[0].isdigit():
        match=re.match(r'[\d\s\u00a0.,]+',value)
        result=Decimal(re.sub(r'\s','',match[0]).replace(',','.'))
        suffix=value[match.end():].strip()
        return result*(1000000 if suffix.startswith(('млн','миллион')) else 1000 if suffix.startswith('тысяч') else 1)
    total=Decimal(0);part=Decimal(0)
    for word in value.split():
        if word in SCALES:total+=(part or 1)*SCALES[word];part=Decimal(0)
        else:part+=WORDS[word]
    return total+part


def quantities(text):
    text=text.lower().replace('ё','е')
    # Число прописью в скобках дублирует значение, а не создаёт ещё одно условие.
    text=re.sub(rf'(\d+)\s*\({WORD}(?:\s+{WORD})*\)',r'\1',text)
    result=[]
    for match in QUANTITY.finditer(text):
        unit=match['unit'];kind=match['kind'] or ''
        if unit.startswith(('дн','день','сут')):unit='days:'+('work' if kind.startswith('рабоч') else 'calendar' if kind else 'unspecified')
        elif unit.startswith('руб'):unit='rubles'
        elif unit.startswith('процент'):unit='percent'
        elif unit.startswith('месяц'):unit='months'
        else:unit='years'
        # Календарный год — не длительность. Номер договора вообще не совпадает с шаблоном единицы.
        if unit=='years' and re.search(r'\b(?:в|от|до|после|с)\s*$',text[max(0,match.start()-12):match.start()]):continue
        result.append((number(match['number']),unit,match.start(),match.end()))
    return result,text


def upper_limit_risks(question, sources):
    asked,_=quantities(question)
    found={}
    for source in sources:
        values,text=quantities(source)
        for value,unit,start,end in values:
            if re.search(r'(?:не\s+более|не\s+превышает)\s*$',text[max(0,start-30):start]):
                found.setdefault(unit,set()).add(value)
    risks=[]
    for value,unit,_,_ in asked:
        limits=found.get(unit,set())
        # Несколько разных ограничений требуют разбора их области действия; не выбираем минимум.
        if len(limits)==1 and value>next(iter(limits)):
            limit=next(iter(limits))
            risks.append(f'запрошено {value}, ограничение {limit}, единица {unit}: проверь действие, условия и исключения нормы; не подтверждай превышение без основания')
    return risks


def affirmative(text):
    # «Не запрещено» не объявляется отрицательным автоматически, но и не становится доказательством права.
    return bool(re.match(r'\s*(?:да\b|можно\b|разрешено\b|допускается\b)',text,re.I))


def asserts(pattern, text):
    for match in re.finditer(pattern,text,re.I):
        prefix=re.split(r'[.!?;\n]',text[:match.start()])[-1]
        if not re.search(r'\b(?:не|нет|нельзя|отсутствует)\b',prefix[-100:],re.I):return True
    return False


def invalid_dates(text):
    result=[]
    for date in re.findall(r'\b\d{1,2}\.\d{1,2}\.\d{4}\b',text):
        try:datetime.strptime(date,'%d.%m.%Y')
        except ValueError:result.append(date)
    return result
