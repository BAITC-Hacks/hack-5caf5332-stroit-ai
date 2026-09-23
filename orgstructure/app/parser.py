"""Keep verbatim source spans; normalization is only used for matching."""
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
import re
import zipfile
import xml.etree.ElementTree as ET

MAX_BYTES = 15 * 1024 * 1024
MAX_TEXT = 600_000

@dataclass
class Document:
    name: str
    text: str
    paragraphs: list


def normalize(text):
    text = re.sub(r'(?<=[а-яА-Яa-zA-Z])-\s*\n\s*(?=[а-яА-Яa-zA-Z])', '', text)
    text = text.lower().replace('ё', 'е').replace('c ', 'с ')
    return ' '.join(re.findall(r'[а-яa-z0-9]+', text))


def extract_text(name, data):
    if not data or len(data) > MAX_BYTES:
        raise ValueError('Файл пуст или превышает 15 МБ. Выберите меньший документ.')
    ext = Path(name).suffix.lower()
    if ext == '.txt':
        for enc in ('utf-8-sig', 'utf-16', 'cp1251'):
            try:
                result = data.decode(enc)
                if '\x00' not in result:
                    return result
            except UnicodeError:
                pass
        raise ValueError('Не удалось прочитать TXT. Сохраните его в UTF-8.')
    if ext in ('.docx', '.xlsx'):
        try:
            with zipfile.ZipFile(BytesIO(data)) as z:
                if sum(i.file_size for i in z.infolist()) > 40 * 1024 * 1024:
                    raise ValueError('Распакованный документ слишком большой.')
                if ext == '.docx':
                    tree = ET.fromstring(z.read('word/document.xml'))
                    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                    return '\n'.join(''.join(p.itertext()) if not p.findall('.//w:t', ns) else ''.join(t.text or '' for t in p.findall('.//w:t', ns)) for p in tree.findall('.//w:p', ns))
                ns = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                strings = []
                if 'xl/sharedStrings.xml' in z.namelist():
                    strings = [''.join(t.text or '' for t in x.findall('.//s:t', ns)) for x in ET.fromstring(z.read('xl/sharedStrings.xml')).findall('s:si', ns)]
                rows = []
                for path in sorted(x for x in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', x)):
                    for row in ET.fromstring(z.read(path)).findall('.//s:row', ns):
                        cells = []
                        for cell in row.findall('s:c', ns):
                            v = cell.find('s:v', ns)
                            value = v.text if v is not None and v.text else ''
                            if cell.get('t') == 's': value = strings[int(value)]
                            if cell.get('t') == 'inlineStr': value = ''.join(t.text or '' for t in cell.findall('.//s:t', ns))
                            cells.append(value)
                        rows.append(' '.join(cells))
                return '\n'.join(rows)
        except (zipfile.BadZipFile, KeyError, ET.ParseError, IndexError) as exc:
            raise ValueError('Повреждённый документ Office. Откройте его и сохраните заново.') from exc
    if ext == '.pdf':
        from pypdf import PdfReader
        try:
            reader = PdfReader(BytesIO(data))
            if reader.is_encrypted:
                raise ValueError('PDF защищён паролем. Загрузите незашифрованную копию.')
            if len(reader.pages) > 250:
                raise ValueError('PDF превышает 250 страниц. Разделите комплект.')
            text = '\n'.join(p.extract_text() or '' for p in reader.pages)
            if len(text.strip()) < 20:
                raise ValueError('В PDF нет текстового слоя. Выполните OCR или загрузите DOCX/TXT.')
            return text
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError('Не удалось разобрать PDF. Загрузите DOCX или TXT.') from exc
    raise ValueError('Поддерживаются DOCX, PDF с текстовым слоем, TXT и XLSX.')


def parse(name, data):
    text = extract_text(name, data)
    if not text.strip() or len(text) > MAX_TEXT:
        raise ValueError('Документ пуст или содержит больше 600 000 символов.')
    # Recognize inline glued clauses only after sentence punctuation, not references.
    pattern = re.compile(r'(?m)(?:^\s*|(?<=[.;])\s+)(?P<n>\d+(?:\.\d+)*\.|[а-я]\.)\s+(?=\S)')
    matches = list(pattern.finditer(text))
    paragraphs, seen, parent = [], set(), ''
    for i, m in enumerate(matches):
        clause = m.group('n').rstrip('.')
        start = m.start('n')
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        raw = text[start:end].rstrip()
        # Tail TOC is often unlabelled; repeated chapter heading + page is sufficient.
        if clause.isdigit() and clause in seen and re.search(r'\s\d+\s*$', raw):
            break
        if clause[0].isdigit():
            seen.add(clause)
            parent = clause
        else:
            clause = parent + '.' + clause
        cut = re.search(r'(?im)^\s*(?:содержание|оглавление)\s*$', raw)
        if cut: raw = raw[:cut.start()].rstrip()
        body = raw[len(m.group('n')):].strip()
        if not normalize(body): continue
        paragraphs.append({'doc': name, 'section': clause.split('.')[0], 'clause': clause,
                           'text': body, 'quote': raw, 'paragraph': text.count('\n', 0, start)+1,
                           'start': start, 'end': start+len(raw)})
        if cut: break
    if not paragraphs:
        # Unnumbered documents remain inspectable, without invented clause numbers.
        offset = 0
        for line in text.splitlines(keepends=True):
            if line.strip():
                begin = offset + len(line)-len(line.lstrip())
                raw = line.strip()
                paragraphs.append({'doc':name, 'section':'', 'clause':'без номера', 'text':raw, 'quote':raw,
                                   'paragraph':text.count('\n',0,begin)+1, 'start':begin, 'end':begin+len(raw)})
            offset += len(line)
    if len(paragraphs) > 1800:
        raise ValueError('Слишком много пунктов. Разделите комплект на части.')
    return Document(name, text, paragraphs)


def reference(p, unit='', relation='direct'):
    return {k:p[k] for k in ('doc','clause','quote','paragraph','start','end')} | {'unit':unit, 'relation':relation}


def extract_units(doc):
    units = []
    # Names are extracted from the actual structural list, never a dictionary of demo names.
    for original in doc.paragraphs:
        p = dict(original)
        if re.search(r'состоит из|в состав .{0,60}вход|структура .{0,60}включ', p['text'], re.I):
            p['text'] = '\n'.join([original['text']] + [x['text'] for x in doc.paragraphs if x['clause'].startswith(original['clause']+'.')])
            for m in re.finditer(r'(?im)(?:^|\n)\s*[–—\-•]?\s*((?:департамент|отдел|управление|служба|бюро|центр)[^\n;]*?)\s*\((?:далее\s*[–—-]?\s*)?([А-ЯA-Z][А-ЯA-Z0-9-]{1,14})\)', p['text']):
                source = next((x for x in doc.paragraphs if m.group(2) in x['text'] and x['clause'].startswith(original['clause']+'.')), original)
                units.append({'name':m.group(1).strip(), 'abbr':m.group(2), 'kind':'unit', 'ref':reference(source,m.group(2))})
    for p in doc.paragraphs:
        name = p['text'].strip().rstrip(':')
        if re.match(r'^(?:Директор(?:ы)?|Начальник|Руководитель|Отдел|Департамент|Управление|Служба|Бюро|Центр)\b', name, re.I) and len(name)<200 and p['text'].endswith(':'):
            if re.search(r'обязан|име[ею]т право', name, re.I): continue
            existing = next((u for u in units if normalize(u['name']).split(' ',1)[-1] in normalize(name) or (u['abbr'] and re.search(r'\b'+re.escape(u['abbr'])+r'\b', name))), None)
            abbrs = [u['abbr'] for u in units if u['abbr'] and re.search(r'\b'+re.escape(u['abbr'])+r'\b',name)]
            if existing and len(abbrs)<=1: continue
            units.append({'name':name,'abbr':' / '.join(abbrs) if abbrs else '', 'kind':'unit' if re.match(r'^(?:Отдел|Департамент|Управление|Служба|Бюро|Центр)\b',name,re.I) else 'role', 'ref':reference(p,' / '.join(abbrs) if abbrs else name)})
    return list({(normalize(u['name']), u['abbr']):u for u in units}.values())
