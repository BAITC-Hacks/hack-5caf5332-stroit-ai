from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from app.server import Handler

class APITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.base=f'http://127.0.0.1:{cls.server.server_port}'
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()
    def request(self,path,body=None,headers=None):
        return urlopen(Request(self.base+path,data=body,headers=headers or {}),timeout=20)
    def test_health_and_ui(self):
        with self.request('/api/health') as r:self.assertEqual(json.load(r)['status'],'ok')
        with self.request('/') as r:self.assertIn('Контур ответственности',r.read().decode())
    def test_demo_repeat_and_exports(self):
        with self.request('/api/demo',b'') as r:
            data=r.read();self.assertIn('analyze;dur=',r.headers['Server-Timing'])
        with self.request('/api/demo',b'') as r:self.assertEqual(data,r.read())
        report=json.loads(data)
        for fmt in ('html','json'):
            with self.request(f"/api/export/{report['run_id']}?format={fmt}") as r:
                self.assertIn('attachment',r.headers['Content-Disposition'])
                output=r.read()
                if fmt=='json':self.assertEqual(json.loads(output),report)
                else:self.assertIn('5.4.4',output.decode())
    def test_streaming_progress(self):
        with self.request('/api/demo',b'',{'Accept':'application/x-ndjson'}) as r:items=[json.loads(line) for line in r]
        self.assertEqual(len([i for i in items if 'progress' in i]),5)
        self.assertIn('report',items[-1]);self.assertGreater(items[-1]['elapsed_ms'],0)
    def test_multipart_docx(self):
        boundary='case11-control-boundary';parts=[]
        for side,edition in [('before',8),('after',9)]:
            p=next(Path('data').glob(f'*{edition}*.docx'))
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{side}[]"; filename="edition-{edition}.docx"\r\nContent-Type: application/octet-stream\r\n\r\n'.encode()+p.read_bytes()+b'\r\n')
        body=b''.join(parts)+f'--{boundary}--\r\n'.encode()
        with self.request('/api/analyze',body,{'Content-Type':f'multipart/form-data; boundary={boundary}'}) as r:report=json.load(r)
        self.assertTrue(any(f['before']['clause']=='5.4.4' and f['after']['clause']=='5.3.3' and f['status']=='moved' for f in report['functions']))
    def test_errors(self):
        for path,body,headers,status in [('/api/export/missing?format=json',None,{},404),('/api/analyze',b'bad',{},400),('/api/demo',b'',{'Origin':'https://example.org'},403)]:
            with self.assertRaises(HTTPError) as c:self.request(path,body,headers)
            self.assertEqual(c.exception.code,status)
            self.assertIn('error',json.loads(c.exception.read()))

if __name__=='__main__':unittest.main()
