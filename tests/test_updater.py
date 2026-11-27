import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
from gateway_cli import cli, updater


def archive(version):
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:
        z.writestr('__main__.py',''); z.writestr('gateway_cli/cli.py',''); z.writestr('gateway_cli/__init__.py',f"__version__ = '{version}'")
    return b.getvalue()

def release(tag, pre=False):
    return {'tag_name':tag,'prerelease':pre,'draft':False,'assets':[{'name':n,'browser_download_url':'https://example.invalid'} for n in ('gateway-cli.pyz','gateway-cli.pyz.sha256')]}

class UpdaterTests(unittest.TestCase):
    def test_selection_and_versions(self):
        rows=[release('v1.2.0'),release('v1.3.0-beta.2',True),release('v1.3.0-beta.10',True)]
        self.assertEqual(updater.select_release(rows,'stable')['tag_name'],'v1.2.0')
        self.assertEqual(updater.select_release(rows,'beta')['tag_name'],'v1.3.0-beta.10')
        self.assertEqual(updater.select_release(rows,'stable','v1.3.0-beta.2')['tag_name'],'v1.3.0-beta.2')
        self.assertGreater(updater.version_key('1.3.0'),updater.version_key('1.3.0-beta.10'))
    def test_checksum(self):
        data=archive('1.3.0')
        with patch.object(updater,'fetch',side_effect=[data,hashlib.sha256(data).hexdigest().encode()]): self.assertEqual(updater.package(release('v1.3.0')),data)
        with patch.object(updater,'fetch',side_effect=[data,b'0'*64]):
            with self.assertRaises(ValueError): updater.package(release('v1.3.0'))
    def test_install_and_rollback_preserve_config(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)/'home'; home.mkdir(); (home/'gateway-cli.pyz').write_bytes(archive('1.2.0-beta.3')); (home/'config.json').write_text('unchanged')
            with patch.object(cli,'launcher_bin',return_value=Path(d)/'bin'), patch.object(updater,'releases',return_value=[release('v1.3.0-beta.1',True)]), patch.object(updater,'package',return_value=archive('1.3.0-beta.1')):
                self.assertEqual(cli.main(['--home',str(home),'update']),0)
                self.assertEqual(json.loads((home/'update.json').read_text())['channel'],'beta')
                self.assertEqual(cli.main(['--home',str(home),'update','--rollback']),0)
                self.assertEqual((home/'gateway-cli.pyz').read_bytes(),archive('1.2.0-beta.3'))
                self.assertEqual((home/'config.json').read_text(),'unchanged')
    def test_background_throttle_and_disable(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d)
            with patch.dict(os.environ, {'AXURION_NO_UPDATE_CHECK':'0'}), patch.object(updater.subprocess,'Popen') as spawn:
                updater.background(home,'1.0.0',cli.atomic); updater.background(home,'1.0.0',cli.atomic)
                self.assertEqual(spawn.call_count,1)
                (home/'update.json').write_text(json.dumps({'auto_check':False}))
                updater.background(home,'1.0.0',cli.atomic); self.assertEqual(spawn.call_count,1)
    def test_failure_restores_archive(self):
        with tempfile.TemporaryDirectory() as d:
            home=Path(d); old=archive('1.0.0'); (home/'gateway-cli.pyz').write_bytes(old); local=home/'new.pyz'; local.write_bytes(archive('2.0.0'))
            with patch.object(cli,'install_archive',side_effect=OSError('failure')):
                self.assertEqual(cli.main(['--home',str(home),'update',str(local)]),1)
            self.assertEqual((home/'gateway-cli.pyz').read_bytes(),old)
