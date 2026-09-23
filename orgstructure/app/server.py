from collections import OrderedDict
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit, parse_qs
from threading import Lock
from .export import export_json, export_html
from .llm import enhance
from .analysis import analyze, demo_documents
from .parser import parse

ROOT = Path(__file__).resolve().parent.parent
REPORTS = OrderedDict()
REPORT_LOCK = Lock()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Never log document names, text, or secrets.

    def send(self, data, content_type='application/json; charset=utf-8', status=200, headers=None):
        if not isinstance(data, bytes): data = json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'")
        for k,v in (headers or {}).items(): self.send_header(k,v)
        self.end_headers(); self.wfile.write(data)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/api/health': return self.send({'status':'ok','mode':'deterministic'})
        if path.startswith('/api/export/'):
            run_id=path.rsplit('/',1)[-1]
            with REPORT_LOCK: report=REPORTS.get(run_id)
            if report is None:return self.send({'error':'Отчёт не найден. Выполните анализ повторно.'},status=404)
            fmt=parse_qs(urlsplit(self.path).query).get('format',['html'])[0]
            if fmt not in ('html','json'):return self.send({'error':'Доступны HTML и JSON. HTML можно открыть в Word или распечатать.'},status=400)
            data=export_html(report) if fmt=='html' else export_json(report)
            return self.send(data,'text/html; charset=utf-8' if fmt=='html' else 'application/json; charset=utf-8',headers={'Content-Disposition':f'attachment; filename=report-{run_id}.{fmt}'})
        paths = {'/':'index.html','/style.css':'style.css','/app.js':'app.js'}
        if path in paths:
            file = ROOT/'static'/paths[path]
            mime={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8'}
            return self.send(file.read_bytes(),mime[file.suffix])
        self.send({'error':'Не найдено.'},status=404)

    def setup(self):
        super().setup()
        self.connection.settimeout(120)

    def do_POST(self):
        origin = self.headers.get('Origin')
        if origin and urlsplit(origin).netloc != self.headers.get('Host'):
            return self.send({'error':'Запрос с другого сайта запрещён.'},status=403)
        started = time.perf_counter()
        streaming=False
        def event(data):
            self.wfile.write((json.dumps(data,ensure_ascii=False)+'\n').encode());self.wfile.flush()
        try:
            length = int(self.headers.get('Content-Length','0'))
            if length < 0 or length > 32*1024*1024: raise ValueError('Комплект превышает 32 МБ.')
            if self.path == '/api/demo':
                before,after=demo_documents()
            elif self.path == '/api/analyze':
                content_type=self.headers.get('Content-Type','')
                if 'multipart/form-data' not in content_type: raise ValueError('Загрузите файлы через форму multipart.')
                message=BytesParser(policy=default).parsebytes(('Content-Type: '+content_type+'\r\n\r\n').encode()+self.rfile.read(length))
                sides={'before[]':[],'after[]':[]}
                for part in message.iter_parts():
                    side=part.get_param('name',header='content-disposition')
                    name=part.get_filename()
                    if side in sides and name:
                        name=Path(name.replace('\\','/')).name
                        docs=sides[side]
                        if any(d.name==name for d in docs): raise ValueError('Имена файлов внутри редакции должны отличаться.')
                        docs.append(parse(name,part.get_payload(decode=True)))
                before,after=sides['before[]'],sides['after[]']
                if not before or not after: raise ValueError('Добавьте хотя бы один документ в обе редакции.')
                if len(before)+len(after)>12: raise ValueError('Допускается не более 12 файлов.')
            else: return self.send({'error':'Не найдено.'},status=404)
            if sum(len(d.paragraphs) for d in before+after)>2400:raise ValueError('Комплект превышает 2400 пунктов. Разделите анализ.')
            streaming='application/x-ndjson' in self.headers.get('Accept','')
            if streaming:
                self.send_response(200)
                self.send_header('Content-Type','application/x-ndjson; charset=utf-8')
                self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.end_headers()
            report=enhance(analyze(before,after,lambda name:event({'progress':name}) if streaming else None))
            with REPORT_LOCK:
                REPORTS[report['run_id']]=report
                if len(REPORTS)>20: REPORTS.popitem(last=False)
            if streaming:
                event({'report':report,'elapsed_ms':round((time.perf_counter()-started)*1000)})
                return
            self.send(report,headers={'Server-Timing':f'analyze;dur={(time.perf_counter()-started)*1000:.1f}'})
        except ValueError as exc:
            if streaming:event({'error':str(exc)})
            else:self.send({'error':str(exc)},status=400)
        except (BrokenPipeError,ConnectionResetError):
            return
        except Exception:
            if streaming:
                event({'error':'Ошибка анализа. Проверьте документы и повторите загрузку.'});return
            self.send({'error':'Не удалось обработать комплект. Проверьте формат и целостность файлов.'},status=422)


def serve():
    port=int(os.environ.get('PORT','8000'))
    server=ThreadingHTTPServer((os.environ.get('HOST','127.0.0.1'),port),Handler)
    print(f'Оргструктура: http://localhost:{port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: server.server_close()
