"""Извлечение текста без исполнения содержимого документов."""
import io
import re
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile, BadZipFile

SUPPORTED = {'.pdf','.docx','.txt','.md'}
MAX_TEXT = 500_000


def parse_document(raw: bytes, filename: str) -> tuple[str,str]:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED: raise ValueError('Поддерживаются PDF, DOCX, TXT и MD.')
    try:
        if suffix == '.pdf':
            from pypdf import PdfReader
            if not raw.startswith(b'%PDF-'): raise ValueError('Файл не является PDF.')
            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted: raise ValueError('PDF защищён паролем. Загрузите незашифрованную копию.')
            if len(reader.pages)>500: raise ValueError('В документе больше 500 страниц. Разделите его на части.')
            pages=[]
            for i,page in enumerate(reader.pages):
                pages.append(f'Страница {i+1}\n'+(page.extract_text() or ''))
                if sum(map(len,pages))>MAX_TEXT: raise ValueError('Слишком много текста. Разделите документ на части.')
            if sum(len(p.split('\n',1)[1].strip()) for p in pages)<20:
                raise ValueError('В PDF нет текстового слоя. Сначала распознайте скан (OCR) и загрузите его снова.')
            text='\n\n'.join(pages)
        elif suffix == '.docx':
            with ZipFile(io.BytesIO(raw)) as archive:
                if sum(i.file_size for i in archive.infolist())>40*1024*1024: raise ValueError('Распакованный DOCX слишком большой.')
                xml=archive.read('word/document.xml')
                if b'<!DOCTYPE' in xml or b'<!ENTITY' in xml: raise ValueError('Неподдерживаемая структура DOCX.')
                root=ElementTree.fromstring(xml)
            ns='{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
            text='\n'.join(''.join(n.text or '' for n in p.iter(ns+'t')) for p in root.iter(ns+'p'))
        else:
            if b'\x00' in raw: raise ValueError('Ожидается текстовый файл в UTF-8 или Windows-1251.')
            try: text=raw.decode('utf-8-sig')
            except UnicodeDecodeError: text=raw.decode('cp1251')
    except (BadZipFile,KeyError,ElementTree.ParseError,UnicodeDecodeError) as exc:
        raise ValueError('Не удалось прочитать файл. Проверьте его формат и целостность.') from exc
    text=text.replace('\r\n','\n').replace('\r','\n').strip()
    if len(text)<20: raise ValueError('В документе слишком мало текста для поиска.')
    if len(text)>MAX_TEXT: raise ValueError('Слишком много текста. Разделите документ на части.')
    # Тип определяется по началу документа; текст из файла не становится инструкцией модели.
    opening=(Path(filename).stem+'\n'+text[:500]).lower()
    kind='Документ'
    for pattern,label in [(r'договор|соглашение','Договор'),(r'регламент|положение|инструкци','Регламент'),(r'федеральный закон|кодекс|постановление|приказ','Нормативный акт')]:
        if re.search(pattern,opening): kind=label;break
    return text,kind
