import json
from pathlib import Path
import unittest
from app.analysis import analyze, demo_documents
from app.parser import parse, normalize
from app.matching import valid_reference

class DemoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.before,cls.after=demo_documents()
        cls.report=analyze(cls.before,cls.after)

    def test_units(self):
        units={u['abbr']:u['status'] for u in self.report['units'] if u['kind']=='unit'}
        self.assertEqual(units,{'ДИТААД':'created','ДОА':'created','ДНМ':'kept','ДККМ':'kept'})
        role=next(u for u in self.report['units'] if u['name']=='Директор направления внутреннего аудита')
        self.assertEqual(role['status'],'transformed')
        self.assertIn('ДИТААД и ДОА',role['after_name'])
        self.assertFalse(any(u['status']=='abolished' for u in self.report['units']))

    def test_transfer_not_loss(self):
        f=next(f for f in self.report['functions'] if f['before']['clause']=='5.4.4')
        self.assertEqual((f['status'],f['after']['clause']),('moved','5.3.3'))

    def test_every_finding_has_verbatim_sources(self):
        for key,old,new in [('units','before_ref','after_ref'),('functions','before','after')]:
            for row in self.report[key]:
                self.assertTrue(valid_reference(row[old],self.before),row)
                self.assertTrue(valid_reference(row[new],self.after),row)
        self.assertEqual(self.report['verification']['rejected'],0)

    def test_identical_json(self):
        self.assertEqual(json.dumps(self.report,ensure_ascii=False,sort_keys=True),json.dumps(analyze(self.before,self.after),ensure_ascii=False,sort_keys=True))

    def test_docx(self):
        for p in Path('data').glob('*.docx'):
            doc=parse(p.name,p.read_bytes())
            self.assertGreater(len(doc.paragraphs),400)
            self.assertTrue(all(x['quote'] in doc.text for x in doc.paragraphs))

    def test_dirty_text(self):
        d=parse('dirty.txt','1. Функции\n1.1. Отдел контроля:\n1.1.1. Проверяет доку-\nменты. 1.1.2. Готовит отчёты.\n1.1.3. ;\nОглавление\n1. ФУНКЦИИ 1'.encode())
        self.assertIn('1.1.2',[p['clause'] for p in d.paragraphs])
        self.assertNotIn('1.1.3',[p['clause'] for p in d.paragraphs])
        self.assertIn('документы',normalize(d.paragraphs[2]['text']))
        self.assertEqual(sum(p['clause']=='1' for p in d.paragraphs),1)

if __name__=='__main__': unittest.main()
