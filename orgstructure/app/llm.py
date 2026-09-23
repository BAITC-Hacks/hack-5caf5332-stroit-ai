"""Optional constrained editor: model may select only verified phrasing variants."""
import copy
import json
import os
from urllib.request import Request, urlopen


def variants(text):
    alternative=text.replace('В новой редакции появились','В новой редакции добавлены').replace('Выявлено преобразований ролей','Найдено преобразований ролей').replace('Требуют ручной проверки на возможную потерю','Нужно вручную проверить на возможную потерю').replace('Найдено потенциальных пересечений ответственности','Обнаружено возможных пересечений ответственности')
    return list(dict.fromkeys([text,alternative]))


def apply_choices(report,choices):
    facts=report['conclusion']
    if not isinstance(choices,dict) or set(choices)!={c['id'] for c in facts}:raise ValueError('Unknown facts')
    result=copy.deepcopy(report)
    for c in result['conclusion']:
        index=choices[c['id']]
        options=variants(c['text'])
        if type(index) is not int or not 0<=index<len(options):raise ValueError('Unknown wording')
        c['text']=options[index]
    result['mode']='llm-assisted'
    result['llm']={'status':'verified','scope':'Выбор формулировок из проверенных вариантов; факты и цитаты неизменны.'}
    return result


def enhance(report):
    key=os.environ.get('OPENAI_API_KEY')
    if not key or os.environ.get('ENABLE_LLM')!='1':return report
    try:
        payload={'model':os.environ.get('OPENAI_MODEL','gpt-4.1-mini'),'store':False,
                 'instructions':'You are a Russian copy editor. Return only a JSON object mapping each supplied fact id to the integer index of its clearest phrasing variant. Do not invent ids, facts, or text.',
                 'input':json.dumps({c['id']:variants(c['text']) for c in report['conclusion']},ensure_ascii=False),
                 'max_output_tokens':300}
        req=Request('https://api.openai.com/v1/responses',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
        with urlopen(req,timeout=12) as response:data=json.load(response)
        output=''.join(c.get('text','') for item in data.get('output',[]) for c in item.get('content',[]) if c.get('type')=='output_text')
        return apply_choices(report,json.loads(output))
    except Exception:
        result=copy.deepcopy(report)
        result['llm']={'status':'fallback','scope':'LLM недоступна или ответ не прошёл проверку; сохранён детерминированный результат.'}
        return result
