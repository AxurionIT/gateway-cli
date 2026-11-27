import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from gateway_cli import cli
from gateway_cli.harnesses import HARNESSES
from gateway_cli.harnesses.managed import update_provider

class HarnessIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'axurion'
        self.env = patch.dict(os.environ, {'XDG_CONFIG_HOME': self.tmp.name, 'PI_CODING_AGENT_DIR': str(Path(self.tmp.name)/'pi'), 'AXURION_API_KEY':'test-secret'})
        self.env.start(); self.addCleanup(self.env.stop)
        cli.save_config(self.home, {'base_url':'https://example.org/v1','model':'astra-coding','effort':'medium','storage':'env'})
    def run_cli(self,*args): return cli.main(['--home',str(self.home),*args])
    def test_sync_preserves_and_launches_without_secret_in_args(self):
        path=HARNESSES['opencode'].path(); path.parent.mkdir(parents=True)
        path.write_text(json.dumps({'agents':{'keep':{}},'providers':{'other':{'name':'Other'}}}))
        with patch.object(cli,'request',return_value=({'data':[{'id':'astra-coding'}]},1)):
            self.assertEqual(self.run_cli('sync','opencode'),0)
            before=path.read_bytes(); self.assertEqual(self.run_cli('sync','opencode'),0); self.assertEqual(before,path.read_bytes())
        d=json.loads(path.read_text()); self.assertIn('other',d['providers']); self.assertIn('keep',d['agents'])
        with patch.object(type(HARNESSES['opencode']),'detect',return_value='/bin/opencode'), patch.object(cli.subprocess,'call',return_value=0) as call:
            self.assertEqual(self.run_cli('--effort','high'),0)
            args, kwargs=call.call_args; self.assertIn('axurion/astra-coding#high',args[0]); self.assertNotIn('test-secret',str(args)); self.assertEqual(kwargs['env']['AXURION_API_KEY'],'test-secret')
        self.assertEqual(self.run_cli('uninstall','opencode'),0)
        d=json.loads(path.read_text()); self.assertIn('other',d['providers']); self.assertNotIn('axurion',d['providers'])
    def test_conflict_and_failure_recovery(self):
        path=Path(self.tmp.name)/'config.json'; receipt=Path(self.tmp.name)/'receipt'
        update_provider(path,receipt,'providers',{'a':1},cli.atomic)
        def fail_config(p,content):
            if p==path: raise OSError('injected')
            cli.atomic(p,content)
        with self.assertRaises(OSError): update_provider(path,receipt,'providers',{'a':2},fail_config)
        update_provider(path,receipt,'providers',{'a':2},cli.atomic)
        doc=json.loads(path.read_text()); doc['providers']['axurion']['a']=3; path.write_text(json.dumps(doc))
        with self.assertRaises(ValueError): update_provider(path,receipt,'providers',None,cli.atomic,True)
    def test_jsonc_is_not_overwritten(self):
        path=HARNESSES['opencode'].path().with_suffix('.jsonc'); path.parent.mkdir(parents=True); path.write_text('// original')
        with patch.object(cli,'request',return_value=({'data':[{'id':'astra-coding'}]},1)):
            self.assertEqual(self.run_cli('sync','opencode'),1)
        self.assertEqual(path.read_text(),'// original')

class AdditionalHarnessTests(HarnessIntegration):
    def test_pi_launch_disables_unverified_thinking(self):
        model={'id':'astra-coding','context_window':100000,'max_output_tokens':8000}
        with patch.object(cli,'request',return_value=({'data':[model]},1)):
            self.assertEqual(self.run_cli('sync','pi'),0)
        with patch.object(type(HARNESSES['pi']),'detect',return_value='/bin/pi'), patch.object(cli.subprocess,'call',return_value=0) as call:
            self.assertEqual(self.run_cli('pi'),0)
            self.assertIn('off',call.call_args.args[0]); self.assertEqual(call.call_args.kwargs['env']['AXURION_API_KEY'],'test-secret')
            self.assertEqual(self.run_cli('pi','--effort','high'),1)
    def test_claude_process_isolation(self):
        self.assertEqual(self.run_cli('sync','claude'),0)
        with patch.object(type(HARNESSES['claude']),'detect',return_value='/bin/claude'), patch.object(cli.subprocess,'call',return_value=0) as call:
            self.assertEqual(self.run_cli('claude','--model','claude-sonnet-4-5','--effort','high'),0)
            env=call.call_args.kwargs['env']; self.assertEqual(env['ANTHROPIC_BASE_URL'],'https://example.org'); self.assertEqual(env['ANTHROPIC_AUTH_TOKEN'],'test-secret'); self.assertNotIn('test-secret',str(call.call_args.args))

class GatewayRequestTests(unittest.TestCase):
    def test_models_and_reasoning_requests_without_socket(self):
        class Response:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, limit): return b'{"data":[{"id":"astra-coding"}]}'
        class Opener:
            calls=[]
            def open(self, req, timeout): self.calls.append(req); return Response()
        opener=Opener()
        with patch('gateway_cli.cli.urllib.request.build_opener',return_value=opener):
            c={'base_url':'https://example.test/v1'}
            cli.request(c,'fake','/models')
            cli.request(c,'fake','/responses',{'model':'astra-coding','reasoning':{'effort':'high'}},session='test-session')
        self.assertEqual(opener.calls[0].full_url,'https://example.test/v1/models')
        self.assertEqual(json.loads(opener.calls[1].data)['reasoning']['effort'],'high')
        self.assertEqual(opener.calls[1].get_header('X-axurion-session-id'),'test-session')

class ManagedStateTests(HarnessIntegration):
    def test_changed_provider_is_not_reported_configured(self):
        with patch.object(cli, 'request', return_value=({'data':[{'id':'astra-coding'}]},1)):
            self.assertEqual(self.run_cli('sync','opencode'),0)
        adapter=HARNESSES['opencode']
        self.assertTrue(adapter.configured(self.home))
        doc=json.loads(adapter.path().read_text())
        doc['providers']['axurion']['name']='modified'
        adapter.path().write_text(json.dumps(doc))
        self.assertFalse(adapter.configured(self.home))
        with patch.object(type(adapter),'detect',return_value='/bin/opencode'), patch.object(cli.subprocess,'call') as call:
            self.assertEqual(self.run_cli('opencode'),1)
            call.assert_not_called()

    def test_sync_all_continues_after_catalogue_failure(self):
        with patch.object(cli,'request',side_effect=cli.CLIError('offline')), patch.object(cli,'codex_home',return_value=Path(self.tmp.name)/'codex'):
            self.assertEqual(self.run_cli('sync'),1)
            self.assertTrue(HARNESSES['claude'].configured(self.home))
            self.assertTrue((Path(self.tmp.name)/'codex'/'axurion.config.toml').exists())

    def test_missing_provider_removes_stale_receipt(self):
        adapter=HARNESSES['opencode']
        with patch.object(cli,'request',return_value=({'data':[{'id':'astra-coding'}]},1)):
            self.assertEqual(self.run_cli('sync','opencode'),0)
        adapter.path().write_text('{"providers": {}}')
        self.assertEqual(self.run_cli('uninstall','opencode'),0)
        self.assertFalse(adapter.state(self.home).exists())

class BasicFlows(HarnessIntegration):
    def test_pi_sync_without_limits_uses_pi_defaults(self):
        with patch.object(cli,'request',return_value=({'data':[{'id':'astra-coding'},{'id':'astra-fast'}]},1)):
            self.assertEqual(self.run_cli('sync','pi'),0)
        models=json.loads(HARNESSES['pi'].path().read_text())['providers']['axurion']['models']
        self.assertEqual([m['id'] for m in models],['astra-coding','astra-fast'])
        self.assertNotIn('contextWindow',models[0])
        self.assertNotIn('maxTokens',models[0])
    def test_interactive_launch_can_configure_opencode(self):
        adapter=HARNESSES['opencode']
        with patch.object(type(adapter),'detect',return_value='/bin/opencode'), patch.object(cli.sys.stdin,'isatty',return_value=True), patch('builtins.input',return_value=''), patch.object(cli,'request',return_value=({'data':[{'id':'astra-coding'}]},1)), patch.object(cli.subprocess,'call',return_value=0) as run:
            self.assertEqual(self.run_cli(),0)
            self.assertTrue(adapter.configured(self.home))
            self.assertIn('axurion/astra-coding#medium',run.call_args.args[0])
    def test_setup_survives_codex_conflict(self):
        ch=Path(self.tmp.name)/'codex'; ch.mkdir(); (ch/'axurion.config.toml').write_text('unmanaged')
        with patch.object(cli,'codex_home',return_value=ch), patch.object(cli.sys.stdin,'isatty',return_value=False):
            self.assertEqual(self.run_cli('setup','--url','https://example.org/v1','--storage','env'),0)
        self.assertEqual((ch/'axurion.config.toml').read_text(),'unmanaged')
