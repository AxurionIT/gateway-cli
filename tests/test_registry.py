import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

from gateway_cli import cli
from gateway_cli.core.model_registry import parse_catalogue
from gateway_cli.harnesses import HARNESSES

class RegistryTests(unittest.TestCase):
    def test_catalogue_filters_invalid_and_private_fields(self):
        models = parse_catalogue({'data': [{'id': 'astra-coding', 'secret': 'do-not-save', 'context_window': 123}, {'id': 'bad id'}]})
        self.assertEqual([m.id for m in models], ['astra-coding'])
        self.assertEqual(models[0].metadata, {'context_window': 123})

    def test_invalid_catalogue(self):
        with self.assertRaises(ValueError): parse_catalogue({'data': {}})

    def test_detection(self):
        with patch('gateway_cli.harnesses.base.shutil.which', return_value='/bin/opencode') as which:
            self.assertEqual(HARNESSES['opencode'].detect(), '/bin/opencode')
            which.assert_called_once_with('opencode')

    def test_default_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            cli.save_config(home, {'base_url': 'https://example.com/v1', 'model': 'astra-coding', 'effort': 'medium', 'storage': 'env'})
            self.assertEqual(cli.main(['--home', tmp, 'default', 'pi']), 0)
            self.assertEqual(cli.config(home)['default_harness'], 'pi')
