"""Isolated local HTTP contract checks; does not control a browser."""
import http.client
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import server


class API(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.DATA={"rows":23441}
        cls.http=server.ThreadingHTTPServer(("127.0.0.1",0),server.Handler)
        cls.port=cls.http.server_port
        cls.thread=threading.Thread(target=cls.http.serve_forever,daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown();cls.http.server_close();cls.thread.join()

    def setUp(self):
        with server.LOCK:
            server.STATE.clear();server.STATE.update(status="complete",run_id="test-run")
            server.ARTIFACTS.clear();server.ARTIFACTS.update({"run.json":b'{"run_id":"test-run"}',"submission.csv":b"target_tariff,channel\ntariff_2,sms\n"})

    def request(self,path,method="GET",headers=None,body=None):
        conn=http.client.HTTPConnection("127.0.0.1",self.port,timeout=2)
        conn.request(method,path,body=body,headers=headers or {})
        response=conn.getresponse();data=response.read();status=response.status
        conn.close();return status,data

    def test_profile_is_aggregate_only(self):
        status,body=self.request("/api/data");self.assertEqual(status,200)
        self.assertEqual(json.loads(body),{"rows":23441})

    def test_source_files_are_not_served(self):
        for path in ["/engine/customer_profile.csv","/server.py","/../engine/agent.py"]:
            self.assertEqual(self.request(path)[0],404)

    def test_wrong_origin_cannot_run(self):
        self.assertEqual(self.request("/api/run","POST",{"Origin":"https://untrusted.invalid"},"{}")[0],403)

    def test_wrong_host_rejected(self):
        self.assertEqual(self.request("/api/data",headers={"Host":"untrusted.invalid"})[0],403)

    def test_stale_run_export_rejected(self):
        self.assertEqual(self.request("/api/export.csv?run_id=old")[0],409)
        status,body=self.request("/api/export.csv?run_id=test-run")
        self.assertEqual(status,200);self.assertIn(b"tariff_2,sms",body)

    def test_double_run_rejected(self):
        release=threading.Event()
        with patch.object(server,"worker",lambda:release.wait(1)):
            headers={"Origin":f"http://127.0.0.1:{self.port}","Content-Type":"application/json"}
            self.assertEqual(self.request("/api/run","POST",headers,"{}")[0],202)
            self.assertEqual(self.request("/api/run","POST",headers,"{}")[0],409)
            release.set()

    def test_worker_error_visible_and_retryable(self):
        with patch.object(server,"command",side_effect=RuntimeError("test failure")):
            server.worker()
        self.assertEqual(server.STATE["status"],"error")
        self.assertEqual(self.request("/api/result")[0],409)


if __name__=="__main__":unittest.main(verbosity=2)
