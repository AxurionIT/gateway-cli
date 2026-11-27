import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from gateway_cli import cli

class YoloTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.home=Path(self.tmp.name)
        self.config={'base_url':'https://example.com/v1','model':'claude-test','effort':'medium','storage':'env','default_harness':'opencode'}
        self.patches=[patch.object(cli,'config',return_value=self.config),patch.object(cli,'get_key',return_value='key'),patch.object(cli.updater,'background'),patch.object(cli.subprocess,'call',return_value=0),patch.object(cli.shutil,'which',return_value='/bin/codex'),patch.object(cli,'codex_home',return_value=self.home),patch.object(cli,'write_profile')]
        for p in self.patches: p.start()
        self.addCleanup(self.tmp.cleanup)
        for p in self.patches: self.addCleanup(p.stop)
    def run_cli(self,*args):
        err=io.StringIO()
        with contextlib.redirect_stderr(err): result=cli.main(['--home',str(self.home),*args])
        return result,err.getvalue()
    def test_default_and_explicit_harnesses(self):
        for name,flag in [('opencode','--auto'),('claude','--dangerously-skip-permissions'),('codex','--dangerously-bypass-approvals-and-sandbox')]:
            with self.subTest(name=name), patch.object(cli.HARNESSES.get(name),'detect',return_value='/bin/'+name) if name!='codex' else contextlib.nullcontext(), patch.object(cli.HARNESSES.get(name),'configured',return_value=True) if name!='codex' else contextlib.nullcontext():
                self.config['default_harness']=name
                rc,warning=self.run_cli('--yolo','--model','claude-test','--effort','high')
                self.assertEqual(rc,0); self.assertIn('YOLO ativo',warning)
                self.assertEqual(cli.subprocess.call.call_args.args[0].count(flag),1)
                rc,warning=self.run_cli(name,'--yolo','--model','claude-test','--effort','high')
                self.assertEqual(rc,0); self.assertIn(flag,cli.subprocess.call.call_args.args[0])
    def test_resume_and_no_duplicate(self):
        rc,_=self.run_cli('codex','resume','--yolo','--dangerously-bypass-approvals-and-sandbox','abc')
        command=cli.subprocess.call.call_args.args[0]
        self.assertEqual(rc,0); self.assertEqual(command.count('--dangerously-bypass-approvals-and-sandbox'),1); self.assertIn('resume',command); self.assertIn('abc',command)
    def test_pi_unsupported(self):
        rc,err=self.run_cli('pi','--yolo'); self.assertEqual(rc,1); self.assertIn('não é suportado',err); cli.subprocess.call.assert_not_called()
    def test_default_behavior(self):
        with patch.object(cli.HARNESSES['opencode'],'detect',return_value='/bin/opencode'), patch.object(cli.HARNESSES['opencode'],'configured',return_value=True):
            rc,err=self.run_cli('opencode'); self.assertEqual(rc,0); self.assertNotIn('--auto',cli.subprocess.call.call_args.args[0]); self.assertNotIn('YOLO',err)
