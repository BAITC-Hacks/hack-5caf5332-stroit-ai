from pathlib import Path
import hashlib
import json
from difflib import SequenceMatcher
from .parser import parse, extract_units, normalize, reference
from .matching import match_functions, verify
from .risks import detect_risks, summarize

ROOT = Path(__file__).resolve().parent.parent


def demo_documents():
    return ([parse(p.name, p.read_bytes()) for p in sorted((ROOT/'data').glob('*8*.txt'))],
            [parse(p.name, p.read_bytes()) for p in sorted((ROOT/'data').glob('*9*.txt'))])


def unit_diff(before, after):
    old = [u for d in before for u in extract_units(d)]
    new = [u for d in after for u in extract_units(d)]
    result, used = [], set()
    exact_targets={}
    reserved=set()
    for old_index,a in enumerate(old):
        target=next((i for i,b in enumerate(new) if i not in reserved and a['kind']==b['kind'] and ((a['abbr'] and a['abbr']==b['abbr']) or normalize(a['name'])==normalize(b['name']))),None)
        if target is not None: exact_targets[old_index]=target;reserved.add(target)
    for old_index,a in enumerate(old):
        candidates = [(i,b) for i,b in enumerate(new) if i not in used and (i not in reserved or i==exact_targets.get(old_index)) and a['kind']==b['kind']]
        exact = next(((i,b) for i,b in candidates if (a['abbr'] and a['abbr']==b['abbr']) or normalize(a['name'])==normalize(b['name'])), None)
        if exact:
            i,b = exact; status = 'kept'; used.add(i)
        else:
            scored = sorted([(SequenceMatcher(None,normalize(a['name']),normalize(b['name'])).ratio(),i,b) for i,b in candidates],key=lambda x:(-x[0],x[1]))
            if scored and scored[0][0]>=(.43 if a['kind']=='role' else .78):
                _,i,b=scored[0]; status='transformed'; used.add(i)
            else: b=None; status='abolished'
        context = next((p for d in after for p in d.paragraphs if 'состоит из' in p['text']),after[0].paragraphs[0])
        result.append({'name':a['name'], 'after_name':b['name'] if b else '', 'abbr':a['abbr'], 'kind':a['kind'], 'status':status,
                       'before_ref':a['ref'], 'after_ref':b['ref'] if b else reference(context,relation='context'), 'requires_review':status in ('transformed','abolished')})
    for i,b in enumerate(new):
        if i in used: continue
        context = next((p for d in before for p in d.paragraphs if 'состоит из' in p['text']),before[0].paragraphs[0])
        result.append({'name':b['name'], 'after_name':b['name'], 'abbr':b['abbr'], 'kind':b['kind'], 'status':'created',
                       'before_ref':reference(context,relation='context'), 'after_ref':b['ref'], 'requires_review':True})
    for i,u in enumerate(result): u['id']=f'u{i+1}'
    return result


def analyze(before,after,progress=None):
    progress=progress or (lambda name: None)
    progress('Документы разобраны')
    units=unit_diff(before,after)
    progress('Подразделения извлечены')
    functions=match_functions(before,after)
    progress('Функции сопоставлены')
    identity = json.dumps([[{'name':d.name,'text':d.text} for d in docs] for docs in (before,after)],ensure_ascii=False,sort_keys=True)
    report = {'run_id':hashlib.sha256(identity.encode()).hexdigest()[:20], 'units':units,
            'functions':functions, 'risks':[], 'conclusion':[], 'pipeline':[{'name':'Разбор документов','status':'done'},{'name':'Извлечение подразделений','status':'done'}],
            'mode':'deterministic', 'elapsed_ms':0, 'documents':{'before':[d.name for d in before],'after':[d.name for d in after]}}

    report['pipeline'] += [{'name':'Сопоставление функций','status':'done'},{'name':'Проверка цитат','status':'done'}]
    verify(report,before,after)
    progress('Цитаты проверены')
    detect_risks(report,before,after)
    summarize(report)
    progress('Риски и заключение готовы')
    report['pipeline'] += [{'name':'Риски и заключение','status':'done'}]
    return report
