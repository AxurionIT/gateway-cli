import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import tomllib
import unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from gateway_cli import cli

class MockHandler(BaseHTTPRequestHandler):
    calls=[]
    def log_message(self,*args): pass
    def reply(self,code,data):
        raw=json.dumps(data).encode(); self.send_response(code); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
    def do_GET(self):
        self.calls.append((self.path,self.headers.get('Authorization'),None))
        if self.path=='/v1/redirect':
            self.send_response(302); self.send_header('Location','/v1/models'); self.end_headers(); return
        if self.headers.get('Authorization')!='Bearer fake-key': self.reply(401,{'error':'secret-body'}); return
        self.reply(200,{'data':[{'id':'astra-coding'},{'id':'axurion-flash'}]})
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append((self.path,self.headers.get('Authorization'),data,self.headers.get('X-Axurion-Session-Id')))
        self.reply(200,{'id':'fake','usage':{'total_tokens':3}})

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.home=self.root/'app'; self.ch=self.root/'codex'; self.ch.mkdir(); self.base=self.ch/'config.toml'; self.base.write_text('model = "original"\n',encoding='utf-8')
        self.env=patch.dict(os.environ,{'CODEX_HOME':str(self.ch),'AXURION_HOME':str(self.home)},clear=False); self.env.start(); os.environ.pop('AXURION_API_KEY',None)
        self.c={'base_url':'https://ai.example.test/v1','model':'astra-coding','effort':'medium','storage':'file'}
    def tearDown(self): self.env.stop(); self.tmp.cleanup()
    def out(self,*args):
        o,e=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(o),contextlib.redirect_stderr(e): rc=cli.main(list(args))
        return rc,o.getvalue(),e.getvalue()
    def test_url_default_path(self): self.assertEqual(cli.normalize_url('https://a.example/'),'https://a.example/v1')
    def test_url_rejects_remote_http(self):
        with self.assertRaises(cli.CLIError): cli.normalize_url('http://192.168.0.1:8317/v1')
    def test_url_rejects_credentials(self):
        for url in ['https://u:p@host','https://host?v=1','https://host/#x']:
            with self.assertRaises(cli.CLIError): cli.normalize_url(url)
    def test_loopback(self): self.assertEqual(cli.normalize_url('http://[::1]:8317'),'http://[::1]:8317/v1')
    def test_profile_preserves_base(self):
        p=cli.write_profile(self.home,self.c); parsed=tomllib.loads(p.read_text(encoding='utf-8')); self.assertEqual(parsed['model'],'astra-coding'); self.assertEqual(parsed['model_providers']['axurion_gateway']['wire_api'],'responses'); self.assertEqual(self.base.read_text(encoding='utf-8'),'model = "original"\n')
    def test_profile_refuses_unmanaged(self):
        (self.ch/'axurion.config.toml').write_text('model="custom"')
        with self.assertRaises(cli.CLIError): cli.write_profile(self.home,self.c)
    def test_profile_refuses_conflict(self):
        self.base.write_text('[model_providers.axurion_gateway]\nname="custom"')
        with self.assertRaises(cli.CLIError): cli.write_profile(self.home,self.c)
    def test_profile_backup(self):
        cli.write_profile(self.home,self.c); cli.write_profile(self.home,dict(self.c,effort='high')); self.assertEqual(len(list(self.ch.glob('*.bak'))),1)
    def test_legacy_profile_migration(self):
        (self.ch/'axurion.config.toml').write_text(cli.OLD_MARK+'\nmodel="old"\n'); cli.write_profile(self.home,self.c); self.assertEqual(len(list(self.ch.glob('*.bak'))),1)
    def test_file_storage_logout(self):
        cli.save_config(self.home,self.c); cli.store_key(self.home,'file','fake-key'); self.assertEqual(cli.get_key(self.home,self.c),'fake-key'); self.assertEqual(self.out('logout')[0],0); self.assertFalse((self.home/'gateway.key').exists())
    def test_no_secret_config(self):
        cli.save_config(self.home,self.c); cli.store_key(self.home,'file','fake-key'); self.assertNotIn('fake-key',self.out('config')[1]); self.assertNotIn('fake-key',(self.home/'config.json').read_text())
    def test_env_storage(self):
        c=dict(self.c,storage='env'); cli.save_config(self.home,c)
        with patch.dict(os.environ,{'AXURION_API_KEY':'fake-key'}): self.assertEqual(cli.get_key(self.home,c),'fake-key')
    def test_invalid_key(self):
        for k in ['','a b','a\nb']:
            with self.assertRaises(cli.CLIError): cli.valid_key(k)
    def test_setup_offline(self):
        with patch('gateway_cli.cli.secret_prompt',return_value='fake-key'),patch('gateway_cli.cli.request',side_effect=AssertionError('network forbidden')):
            rc,out,err=self.out('setup','--url',self.c['base_url'],'--storage','file'); self.assertEqual(rc,0,err); self.assertIn('Nenhuma inferência',out)
    def test_usage_scope(self):
        cli.save_config(self.home,self.c); cli.append_usage(self.home,self.c,{'usage':{'total_tokens':5}},12,'astra-coding','medium'); rc,out,err=self.out('usage','--json'); self.assertEqual(json.loads(out)['total_tokens_reported'],5)
    def test_dashboard(self): self.assertEqual(cli.dashboard_url(self.c),'https://ai.example.test/v0/resource/plugins/axurion-intelligent-router/admin')
    def test_codex_args(self):
        cli.save_config(self.home,self.c); cli.store_key(self.home,'file','fake-key')
        with patch('gateway_cli.cli.shutil.which',return_value='/fake/codex'),patch('gateway_cli.cli.subprocess.call',return_value=0) as run:
            self.assertEqual(self.out('codex','--effort','high','--','exec','hi')[0],0); self.assertIn('model_reasoning_effort="high"',run.call_args[0][0]); self.assertNotIn('fake-key',str(run.call_args))
    def test_http_mock(self):
        srv=ThreadingHTTPServer(('127.0.0.1',0),MockHandler); t=threading.Thread(target=srv.serve_forever,daemon=True); t.start(); MockHandler.calls.clear()
        try:
            c=dict(self.c,base_url=f'http://127.0.0.1:{srv.server_port}/v1'); cli.save_config(self.home,c); cli.store_key(self.home,'file','fake-key')
            self.assertIn('astra-coding',self.out('models')[1]); self.assertEqual(self.out('status')[0],0); self.assertTrue(all(x[0]=='/v1/models' for x in MockHandler.calls))
            self.assertEqual(self.out('test')[0],0); self.assertEqual(len(MockHandler.calls),2)
            rc,o,e=self.out('test','--yes','--effort','high'); self.assertEqual(rc,0,e); self.assertEqual(MockHandler.calls[-1][2]['reasoning']['effort'],'high'); self.assertTrue(MockHandler.calls[-1][3].startswith('axurion-probe-'))
            self.assertEqual(self.out('test','--yes','--protocol','chat')[0],0); self.assertEqual(MockHandler.calls[-1][2]['reasoning_effort'],'medium')
            with self.assertRaises(cli.HTTPError) as ctx: cli.request(c,'bad','/models')
            self.assertEqual(ctx.exception.status,401); self.assertNotIn('secret-body',str(ctx.exception))
            with self.assertRaises(cli.HTTPError) as ctx: cli.request(c,'fake-key','/redirect')
            self.assertEqual(ctx.exception.status,302); self.assertEqual(MockHandler.calls[-1][0],'/v1/redirect')
        finally: srv.shutdown(); srv.server_close(); t.join()
    def test_usage_aggregation_redacts(self):
        result=cli.summarize_server_usage({'provider-secret':{'https://secret|raw-api-key':{'success':12,'failed':2},'another-key':{'success':1,'failed':0}}})
        self.assertEqual(result['success'],13); self.assertEqual(result['failed'],2); self.assertNotIn('secret',str(result)); self.assertNotIn('raw-api-key',str(result))
    def test_install_archive(self):
        import zipfile
        src=self.root/'a.pyz'
        with zipfile.ZipFile(src,'w') as z:
            for name in ('__main__.py','gateway_cli/cli.py','gateway_cli/__init__.py'): z.writestr(name,'# mock')
        with patch('gateway_cli.cli.launcher_bin',return_value=self.root/'bin'):
            target,launch=cli.install_archive(self.home,src); self.assertEqual(target.read_bytes(),src.read_bytes()); self.assertIn('Managed by Axurion Gateway CLI',launch.read_text())

if __name__=='__main__': unittest.main()
