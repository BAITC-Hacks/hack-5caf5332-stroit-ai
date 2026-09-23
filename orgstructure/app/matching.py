from collections import Counter
import math
import re
from . import config
from .parser import normalize, extract_units, reference


def extract_functions(doc):
    units = extract_units(doc)
    result, headings = [], {}
    active=False
    default_owner='Общие функции'
    for p in doc.paragraphs:
        c = p['clause']
        if not re.fullmatch(r'\d+(?:\.\d+)*',c): continue
        depth = len(c.split('.'))
        if depth == 1:
            headings = {}
            active = bool(re.search(r'функци|обязанност|ответственност|задач',p['text'],re.I))
            default_owner = p['text'].split('\n')[-1].rstrip(':') if '\n' in p['text'] else 'Общие функции'
        if depth == 2:
            name = p['text'].strip().rstrip(':')
            is_heading = bool(re.match(r'(?:Директор(?:ы)?|Начальник|Руководитель|Работники|Главный|Отдел|Департамент|Управление|Служба|Бюро|Центр)',name,re.I) and p['text'].endswith(':'))
            if is_heading:
                abbrs = [u['abbr'] for u in units if u['kind']=='unit' and (re.search(r'\b'+re.escape(u['abbr'])+r'\b',name) or normalize(u['name']).split(' ',1)[-1] in normalize(name))]
                owner = ' / '.join(abbrs) if abbrs else re.split(r'\s+(?:обязан(?:ы)?|(?:не )?име(?:ет|ют) право|несут ответственность|информирует)\b',name,maxsplit=1,flags=re.I)[0]
                headings[c] = (owner, 'prohibition' if re.search(r'не имеют права|запрещ',name,re.I) else 'function')
        parent = '.'.join(c.split('.')[:-1])
        if depth < 3 or not (parent in headings or (active and depth==3)): continue
        owner,kind = headings.get(parent,(default_owner,'function'))
        # Include letter subclauses in one contiguous, verbatim span.
        children = [x for x in doc.paragraphs if x['clause'].startswith(c+'.')]
        end = max([p['end']] + [x['end'] for x in children])
        full = dict(p, quote=doc.text[p['start']:end],end=end)
        body = re.sub(r'^\d+(?:\.\d+)*\.\s*','',full['quote'])
        if len(normalize(body)) < 8: continue
        result.append({'text':body,'unit':owner,'clause':c,'kind':kind,'ref':reference(full,owner),
                       'norm':normalize(re.sub(r'(?m)^\s*(?:\d+(?:\.\d+)*|[а-я])\.\s*','',body))})
    return result


class Similarity:
    """Word + character TF-IDF cosine, fitted once over both versions."""
    def __init__(self, texts):
        self.texts = texts
        self.vectors=[]
        for kind in ('word','char'):
            counts=[]
            for text in texts:
                tokens = text.split() if kind=='word' else [text[i:i+4] for i in range(max(0,len(text)-3))]
                counts.append(Counter(tokens))
            df=Counter(t for c in counts for t in c)
            vectors=[]
            for c in counts:
                v={t:(1+math.log(n))*(1+math.log((1+len(texts))/(1+df[t]))) for t,n in c.items()}
                length=math.sqrt(sum(n*n for n in v.values())) or 1
                vectors.append({t:n/length for t,n in v.items()})
            self.vectors.append(vectors)

    def score(self,i,j):
        score=0
        for weight,vs in zip((config.WORD_WEIGHT,config.CHAR_WEIGHT),self.vectors):
            a,b=vs[i],vs[j]
            if len(a)>len(b): a,b=b,a
            score += weight*sum(v*b.get(k,0) for k,v in a.items())
        # Do not silently conflate an action with its explicit negation.
        neg=lambda s: bool(re.search(r'\bне\b|запрещ|не вправе',s))
        if neg(self.texts[i]) != neg(self.texts[j]): score *= .55
        return min(1,max(0,score))


def match_functions(before,after):
    old=[f for d in before for f in extract_functions(d)]
    new=[f for d in after for f in extract_functions(d)]
    sim=Similarity([f['norm'] for f in old+new])
    offset=len(old)
    matches,used={},set()
    # Reserve exact same-owner matches globally before transfers and fuzzy matches.
    for same_owner in (True,False):
        for i,a in enumerate(old):
            if i in matches: continue
            options=[(j,b) for j,b in enumerate(new) if j not in used and a['norm']==b['norm'] and a['kind']==b['kind'] and (not same_owner or a['unit']==b['unit'])]
            if options:
                j,b=min(options,key=lambda x:(x[1]['clause']!=a['clause'],x[0]))
                matches[i]=(j,1.,'exact');used.add(j)
    scores={}
    candidates=[]
    for i,a in enumerate(old):
        for j,b in enumerate(new):
            score=sim.score(i,offset+j) if a['kind']==b['kind'] else 0
            scores[i,j]=score
            if i not in matches and j not in used and score>=config.MATCH_THRESHOLD:
                candidates.append((score + (.025 if a['unit']==b['unit'] else 0),i,j,score))
    for _,i,j,score in sorted(candidates,key=lambda x:(-x[0],x[1],x[2])):
        if i not in matches and j not in used:
            matches[i]=(j,score,'tfidf');used.add(j)
    # Consolidation can be many-to-one: consuming a candidate never proves loss.
    for i,a in enumerate(old):
        if i in matches or not new: continue
        j=max(range(len(new)),key=lambda j:(scores[i,j],a['unit']==new[j]['unit'],-j))
        if scores[i,j]>=config.MATCH_THRESHOLD:
            matches[i]=(j,scores[i,j],'consolidated');used.add(j)
    result=[]
    fallback_before=reference(before[0].paragraphs[0],relation='context')
    fallback_after=reference(after[0].paragraphs[0],relation='context')
    for i,a in enumerate(old):
        if i in matches:
            j,score,method=matches[i];b=new[j]
            status='moved' if a['unit']!=b['unit'] or a['clause']!=b['clause'] else ('kept' if method=='exact' else 'reworded')
            after_ref=b['ref']
        else:
            j=max(range(len(new)),key=lambda j:(scores[i,j],-j)) if new else None
            score=scores[i,j] if j is not None else 0
            after_ref=dict(new[j]['ref'],relation='nearest_candidate') if j is not None else fallback_after
            status,method='lost','below_threshold'
        result.append({'text':a['text'],'status':status,'confidence':round(score,4),'method':method,
                       'before':dict(a['ref'],side='before'),'after':dict(after_ref,side='after'),
                       'requires_review':status=='lost' or method!='exact', 'kind':a['kind']})
    for j,b in enumerate(new):
        if j in used:continue
        i=max(range(len(old)),key=lambda i:(scores[i,j],-i)) if old else None
        ref=dict(old[i]['ref'],relation='nearest_candidate') if i is not None else fallback_before
        result.append({'text':b['text'],'status':'added','confidence':round(scores[i,j],4) if i is not None else 0,
                       'method':'unmatched','before':dict(ref,side='before'),'after':dict(b['ref'],side='after'),'requires_review':True,'kind':b['kind']})
    for i,f in enumerate(result): f['id']=f'f{i+1}'
    return result


def valid_reference(ref,documents):
    return any(d.name==ref['doc'] and d.text[ref['start']:ref['end']]==ref['quote'] and bool(ref['quote'].strip()) for d in documents)


def verify(report,before,after):
    rejected=0
    for key,left,right in [('units','before_ref','after_ref'),('functions','before','after')]:
        good=[]
        for row in report[key]:
            if valid_reference(row[left],before) and valid_reference(row[right],after):
                row['evidence_verified']=True;good.append(row)
            else: rejected+=1
        report[key]=good
    report['verification']={'verified':True,'rejected':rejected,'rule':'Две дословные цитаты; контекст не доказывает отсутствие функции.'}
    return report
