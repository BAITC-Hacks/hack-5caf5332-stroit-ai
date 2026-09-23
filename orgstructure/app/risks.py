import re
from collections import Counter
from .matching import extract_functions, Similarity, valid_reference
from .parser import reference, normalize
from .config import DUPLICATE_THRESHOLD


def detect_risks(report,before,after):
    risks=[]
    def add(kind,explanation,recommendation,evidence,severity='medium',**extra):
        if len(evidence)<2 or not all(valid_reference(e,before if e['side']=='before' else after) for e in evidence):return
        risks.append({'id':f'r{len(risks)+1}','type':kind,'severity':severity,'explanation':explanation,
                      'recommendation':recommendation,'evidence':evidence,'requires_review':True,'evidence_verified':True,**extra})
    for f in report['functions']:
        if f['status']=='lost':
            add('lost',f"Для функции §{f['before']['clause']} ({f['before']['unit']}) не найдено соответствия выше порога. Ближайший кандидат не доказывает отсутствие функции.",
                'Проверить весь комплект, объединение пунктов и приложения; при подтверждении закрепить функцию за конкретным владельцем.',[f['before'],f['after']],'high',function_id=f['id'])
    functions=[f for d in after for f in extract_functions(d) if f['kind']!='prohibition']
    sim=Similarity([f['norm'] for f in functions])
    for i,a in enumerate(functions):
        for j in range(i+1,len(functions)):
            b=functions[j]
            if a['unit']==b['unit']:continue
            score=1 if a['norm']==b['norm'] else sim.score(i,j)
            if score<DUPLICATE_THRESHOLD:continue
            refs=[dict(a['ref'],side='after'),dict(b['ref'],side='after')]
            matches=[f for f in report['functions'] if any(f['after']['doc']==r['doc'] and f['after']['start']==r['start'] and f['after']['relation']=='direct' for r in refs)]
            for f in matches:f['duplicated']=True
            if matches:refs.insert(0,matches[0]['before'])
            add('duplicated',f"У владельцев «{a['unit']}» и «{b['unit']}» похожие обязанности (§{a['clause']} и §{b['clause']}); сходство {round(score*100)}%. Это может быть общей управленческой обязанностью, а не избыточным дублированием.",
                'Уточнить границы ответственности и объект работы; при пересечении назначить одного ответственного, остальных указать как участников.',refs,confidence=round(score,4))
    # A preventative policy is evidence of a safeguard, never evidence of a violation.
    for d in after:
        for p in d.paragraphs:
            if not re.search(r'конфликт.{0,12}интерес|независимост|свою прежн|ранее отвечал',p['text'],re.I):continue
            if len(p['text'])>6000:continue
            context=next((x for old in before for x in old.paragraphs if x['clause']==p['clause']),before[0].paragraphs[0])
            prevention=bool(re.search(r'информиров|раскрыти|исключени|предотвращ|не должны|не могут|не имеют права|запрещ|сохранени.{0,8}независим|обеспеч.{0,20}независим',p['text'],re.I))
            if 'конфликт' in p['text'].lower() or re.search(r'свою прежн|ранее отвечал',p['text'],re.I):
                add('conflict',('В документе предусмотрена мера предотвращения конфликта интересов. Нарушение этим пунктом не установлено.' if prevention else 'Есть упоминание конфликта интересов или прежней зоны ответственности аудитора; требуется проверить конкретные назначения.'),
                    'Проверить декларации независимости, прежние обязанности аудиторов и назначение независимого проверяющего.',
                    [dict(reference(context),side='before'),dict(reference(p),side='after')], 'info' if prevention else 'medium',classification='safeguard' if prevention else 'potential')
    # Same owner executes and controls the same object; common institutional words do not count.
    stop={'общества','общество','функции','функций','работу','работы','работников','обязанности','подразделения','внутреннего','аудита','осуществляет','организует','проверяет','контролирует','выполняет','обеспечивает','ведет','проводит','руководство','процесс','процесса','деятельности','соответствии','настоящего','положения'}
    def objects(f):return {w[:7] for w in normalize(f['text']).split() if len(w)>4 and w not in stop}
    for i,a in enumerate(functions):
        if not re.match(r'(?:выполняет|исполняет|ведет|осуществляет|согласовывает|утверждает|обрабатывает)\b',normalize(a['text'])):continue
        if re.search(r'провер|аудит|контрол',normalize(a['text'])):continue
        for b in functions:
            if a['unit']!=b['unit'] or a is b:continue
            if not re.match(r'(?:проверяет|контролирует|проводит аудит|осуществляет контроль)\b',normalize(b['text'])):continue
            if len(objects(a)&objects(b))<2:continue
            add('conflict',f"«{a['unit']}» исполняет и проверяет сходный объект работы (§{a['clause']}, §{b['clause']}). Возможна самопроверка.",
                'Разделить исполнение и независимую проверку между разными владельцами; проверить фактический объект контроля.',
                [dict(reference(next((p for d in before for p in d.paragraphs if p['clause']==a['clause']),before[0].paragraphs[0]),relation='context'),side='before'),dict(a['ref'],side='after'),dict(b['ref'],side='after')], 'high',classification='potential')
    report['risks']=risks
    return report


def summarize(report):
    uc=Counter(u['status'] for u in report['units'] if u['kind']=='unit')
    fc=Counter(f['status'] for f in report['functions'])
    rc=Counter(r['type'] for r in report['risks'] if r.get('classification')!='safeguard')
    fc['duplicated']=sum(bool(f.get('duplicated')) for f in report['functions'])
    report['counts']={'units':{s:uc[s] for s in ('created','kept','transformed','abolished')},
                      'functions':{s:fc[s] for s in ('kept','moved','reworded','lost','added','duplicated')},
                      'risks':{s:rc[s] for s in ('lost','duplicated','conflict')}}
    facts=[]
    def fact(text,rows,refs):
        if not rows:return
        evidence=list({(e['side'],e['doc'],e['start']):e for row in rows for e in refs(row)}.values());facts.append({'id':f'c{len(facts)+1}','text':text,'evidence':evidence})
    units=report['units'];functions=report['functions']
    ur=lambda u:[dict(u['before_ref'],side='before'),dict(u['after_ref'],side='after')]
    fr=lambda f:[f['before'],f['after']]
    created=[u for u in units if u['status']=='created']
    fact(f"В новой редакции появились подразделения и роли: {', '.join(u['abbr'] or u['name'] for u in created)}.",created,ur)
    kept=[u for u in units if u['status']=='kept']
    fact(f"Сохранены подразделения и роли: {', '.join(u['abbr'] or u['name'] for u in kept)}.",kept,ur)
    transformed=[u for u in units if u['status']=='transformed']
    fact(f"Выявлено преобразований ролей: {len(transformed)}; преемственность требует проверки по обязанностям.",transformed,ur)
    moved=sorted([f for f in functions if f['status']=='moved'],key=lambda f:(f['before']['unit']==f['after']['unit'],-len(f['text'])))
    if moved:
        m=moved[0]
        fact(f"Перенесено или перенумеровано функций: {fc['moved']}; например, §{m['before']['clause']} сопоставлен с §{m['after']['clause']} новой редакции.",moved,fr)
    lost=[f for f in functions if f['status']=='lost']
    fact(f"Требуют ручной проверки на возможную потерю {fc['lost']} функций; отсутствие совпадения не доказывает утрату обязанности.",lost,fr)
    duplicates=[r for r in report['risks'] if r['type']=='duplicated']
    fact(f"Найдено потенциальных пересечений ответственности: {len(duplicates)}; необходимо уточнить объект и границы каждой обязанности.",duplicates,lambda r:r['evidence'])
    conflict=[r for r in report['risks'] if r['type']=='conflict']
    fact(f"Кандидатов на конфликт интересов: {rc['conflict']}; профилактические положения учитываются отдельно и не считаются нарушениями.",conflict,lambda r:r['evidence'])
    # On small control documents, do not pad the conclusion with unsupported sentences.
    if not facts and functions:
        fact(f"Сопоставлено функций: {len(functions)}; проверьте цитаты и границы ответственности.",functions,fr)
    report['conclusion']=facts[:7]
    return report
