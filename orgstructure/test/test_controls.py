from io import BytesIO
import json
import os
import unittest
from unittest.mock import patch
import zipfile
from app.analysis import analyze, demo_documents
from app.parser import parse
from app.matching import valid_reference, verify
from app.llm import apply_choices, enhance, variants
from app.export import export_html, export_json
from test.synthetic import make_synthetic

class ControlTests(unittest.TestCase):
    def test_synthetic_deleted_and_duplicated(self):
        old,new,deleted,copied=make_synthetic()
        before=[parse('before.txt',old.encode())];after=[parse('after.txt',new.encode())]
        report=analyze(before,after)
        loss=next(f for f in report['functions'] if f['before']['clause']==deleted['clause'])
        self.assertEqual(loss['status'],'lost')
        self.assertTrue(loss['requires_review'])
        duplicates=[r for r in report['risks'] if r['type']=='duplicated' and {copied['clause'],'5.5.11'}<={e['clause'] for e in r['evidence']}]
        self.assertTrue(duplicates)
        self.assertTrue(any(f.get('duplicated') and f['after']['clause']=='5.5.11' for f in report['functions']))
        for risk in report['risks']:
            self.assertGreaterEqual(len(risk['evidence']),2)
            for e in risk['evidence']:self.assertTrue(valid_reference(e,before if e['side']=='before' else after))

    def test_generic_owners_conflict(self):
        text='1. Обязанности\n1.1. Отдел платежей:\n1.1.1. Выполняет платежные операции поставщиков.\n1.1.2. Проверяет платежные операции поставщиков.\n1.2. Отдел снабжения:\n1.2.1. Ведет учет складских запасов.'
        d=parse('other.txt',text.encode());r=analyze([d],[d])
        self.assertTrue(any(x['type']=='conflict' and x['classification']=='potential' for x in r['risks']))

    def test_prevention_not_violation(self):
        b,a=demo_documents();r=analyze(b,a)
        self.assertEqual(r['counts']['risks']['conflict'],0)
        self.assertTrue(any(x.get('classification')=='safeguard' for x in r['risks']))

    def test_consolidation_not_loss(self):
        before='1. Обязанности\n1.1. Отдел А:\n1.1.1. Ведет реестр договоров поставщиков.\n1.2. Отдел Б:\n1.2.1. Ведет реестр договоров поставщиков.'
        after='1. Обязанности\n1.1. Отдел В:\n1.1.1. Ведет реестр договоров поставщиков.'
        r=analyze([parse('before.txt',before.encode())],[parse('after.txt',after.encode())])
        self.assertFalse(any(f['status']=='lost' for f in r['functions']))

    def test_negation_not_kept(self):
        old='1. Обязанности\n1.1. Отдел А:\n1.1.1. Выполняет платежные операции поставщиков.'
        new=old.replace('Выполняет','Не выполняет')
        r=analyze([parse('a.txt',old.encode())],[parse('b.txt',new.encode())])
        self.assertFalse(any(f['status']=='kept' for f in r['functions']))

    def test_all_conclusion_sources(self):
        b,a=demo_documents();r=analyze(b,a)
        self.assertTrue(5<=len(r['conclusion'])<=7)
        for c in r['conclusion']:
            self.assertGreaterEqual(len(c['evidence']),2)
            for e in c['evidence']:self.assertTrue(valid_reference(e,b if e['side']=='before' else a))

    def test_tampered_evidence_rejected(self):
        b,a=demo_documents();r=analyze(b,a)
        r['functions'][0]['before']['quote']='НЕСУЩЕСТВУЮЩАЯ ЦИТАТА'
        verify(r,b,a)
        self.assertEqual(r['verification']['rejected'],1)

    def test_llm_validation_and_fallback(self):
        b,a=demo_documents();r=analyze(b,a)
        choices={c['id']:len(variants(c['text']))-1 for c in r['conclusion']}
        edited=apply_choices(r,choices)
        self.assertEqual(edited['functions'],r['functions']);self.assertEqual(edited['mode'],'llm-assisted')
        with self.assertRaises(ValueError):apply_choices(r,{'invented':0})
        bad=dict(choices);bad[next(iter(bad))]=999
        with self.assertRaises(ValueError):apply_choices(r,bad)
        reply={'output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(choices)}]}]}
        with patch.dict(os.environ,{'ENABLE_LLM':'1','OPENAI_API_KEY':'test-placeholder'}),patch('app.llm.urlopen',return_value=BytesIO(json.dumps(reply).encode())) as network:
            self.assertEqual(enhance(r)['mode'],'llm-assisted')
            payload=json.loads(network.call_args[0][0].data)
            self.assertFalse(payload['store'])
            self.assertNotIn('quote',payload['input'])
        with patch.dict(os.environ,{'ENABLE_LLM':'1','OPENAI_API_KEY':'test-placeholder'}),patch('app.llm.urlopen',side_effect=TimeoutError):
            fallback=enhance(r)
            self.assertEqual(fallback['mode'],'deterministic')
            self.assertEqual(fallback['llm']['status'],'fallback')
        with patch.dict(os.environ,{},clear=True),patch('app.llm.urlopen') as network:
            self.assertEqual(enhance(r),r);network.assert_not_called()

    def test_exports_and_html_escape(self):
        b,a=demo_documents();r=analyze(b,a)
        self.assertEqual(json.loads(export_json(r)),r)
        r['functions'][0]['text']='<script>alert(1)</script>'
        html=export_html(r).decode()
        self.assertNotIn('<script>',html);self.assertIn('&lt;script&gt;',html)
        self.assertIn('5.4.4',html);self.assertIn('5.3.3',html)

    def test_invalid_inputs(self):
        for name,data in [('empty.txt',b''),('broken.docx',b'bad'),('x.exe',b'bad')]:
            with self.assertRaises(ValueError):parse(name,data)

    def test_xlsx(self):
        buf=BytesIO()
        with zipfile.ZipFile(buf,'w') as z:
            z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData><row><c t="inlineStr"><is><t>1. Обязанности</t></is></c></row><row><c t="inlineStr"><is><t>1.1. Ведет реестр договоров.</t></is></c></row></sheetData></worksheet>')
        d=parse('a.xlsx',buf.getvalue());self.assertEqual(d.paragraphs[1]['clause'],'1.1')

    def test_pdf_and_scanned_error(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        writer=PdfWriter();page=writer.add_blank_page(600,800)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 40 700 Td (1. Functions) Tj 0 -20 Td (1.1. Reviews supplier documents.) Tj ET')
        page[NameObject('/Contents')]=writer._add_object(stream)
        buf=BytesIO();writer.write(buf)
        self.assertEqual(parse('a.pdf',buf.getvalue()).paragraphs[1]['clause'],'1.1')
        blank=PdfWriter();blank.add_blank_page(600,800);buf=BytesIO();blank.write(buf)
        with self.assertRaisesRegex(ValueError,'OCR'):parse('scan.pdf',buf.getvalue())

if __name__=='__main__':unittest.main()
