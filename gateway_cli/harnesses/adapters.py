"""Harness integration using native configuration, without persisted secrets."""
import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from .base import Harness
from .managed import update_provider, read_json, digest

EFFORTS = ('low', 'medium', 'high', 'xhigh')

class Adapter(Harness):
    def state(self, home): return home / 'harnesses' / (self.name + '.json')
    def configured(self, home):
        try:
            state = read_json(self.state(home))
            if not hasattr(self, 'path'): return state.get('isolated') is True
            provider = read_json(self.path()).get('providers', {}).get('axurion')
            return provider is not None and digest(provider) in (state.get('digest'), state.get('previous_digest'))
        except (OSError, ValueError, TypeError, AttributeError):
            return False
    def sync(self, home, config, models, atomic): raise NotImplementedError
    def uninstall(self, home, atomic): raise NotImplementedError

class OpenCode(Adapter):
    def path(self):
        base = Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'opencode'
        json_path, jsonc_path = base/'opencode.json', base/'opencode.jsonc'
        if json_path.exists() and jsonc_path.exists():
            # OpenCode merges JSON first and JSONC second. Do not shadow an
            # existing provider in the lower-precedence file.
            providers = read_json(json_path).get('providers', {})
            if not isinstance(providers, dict) or 'axurion' in providers:
                raise ValueError('Provider axurion em opencode.json conflita com opencode.jsonc; nenhuma alteração aplicada.')
        return jsonc_path if jsonc_path.exists() else json_path
    def sync(self, home, config, models, atomic):
        # OpenCode v2 custom-provider schema. The raw request body carries
        # reasoning_effort; gateway routing still requires end-to-end validation.
        if not models: raise ValueError('Catálogo vazio; configuração não alterada.')
        variants = [{'id': e, 'body': {'reasoning_effort': e}} for e in EFFORTS]
        provider = {'package': '@opencode/ai/providers/openai-compatible', 'name': 'Axurion AI Gateway',
                    'settings': {'baseURL': config['base_url'], 'apiKey': '{env:AXURION_API_KEY}'},
                    'models': {m.id: {'name': m.id, 'variants': variants} for m in models}}
        update_provider(self.path(), self.state(home), 'providers', provider, atomic)
    def uninstall(self, home, atomic): update_provider(self.path(), self.state(home), 'providers', None, atomic, True)
    def command(self, exe, model, effort, extra):
        return [exe, 'mini', '--standalone', '--model', f'axurion/{model}#{effort}', *extra]

class Codex(Adapter):
    pass

class Pi(Adapter):
    def path(self): return Path(os.environ.get('PI_CODING_AGENT_DIR', Path.home()/'.pi'/'agent'))/'models.json'
    def sync(self, home, config, models, atomic):
        if not models: raise ValueError('Catálogo vazio; configuração não alterada.')
        eligible = []
        missing_limits = False
        for model in models:
            entry = {'id': model.id, 'name': model.id}
            for source, target in (('context_window', 'contextWindow'), ('max_output_tokens', 'maxTokens')):
                value = model.metadata.get(source)
                if type(value) is int and value > 0: entry[target] = value
                else: missing_limits = True
            eligible.append(entry)
        if missing_limits:
            import warnings
            warnings.warn('Pi usará seus limites padrão para modelos sem metadados; confirme-os no gateway antes de usar.', UserWarning)
        provider = {'baseUrl': config['base_url'], 'api': 'openai-responses', 'apiKey': '$AXURION_API_KEY', 'models': eligible}
        update_provider(self.path(), self.state(home), 'providers', provider, atomic)
    def uninstall(self, home, atomic): update_provider(self.path(), self.state(home), 'providers', None, atomic, True)

class Claude(Adapter):
    # Claude is isolated via process environment rather than modifying settings.
    def sync(self, home, config, models, atomic):
        atomic(self.state(home), '{"isolated": true}\n')
    def uninstall(self, home, atomic): self.state(home).unlink(missing_ok=True)
    def command(self, exe, model, effort, extra): return [exe, '--model', model, '--effort', effort, *extra]
    @staticmethod
    def base_url(url):
        parts = urlsplit(url); path = parts.path.rstrip('/')
        if path.endswith('/v1'): path = path[:-3]
        return urlunsplit((parts.scheme, parts.netloc, path, '', ''))
