"""Axurion Gateway CLI. Standard-library core, optional system keyring."""
import argparse
import getpass
import ipaddress
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
import uuid
import warnings
import webbrowser
import zipfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from . import __version__, updater
from .core.model_registry import parse_catalogue
from .harnesses import HARNESSES

MARK = '# Managed by Axurion Gateway CLI'
OLD_MARK = '# Managed by Axurion Gateway Setup'
SERVICE = 'Axurion Gateway CLI'
EFFORTS = ('low', 'medium', 'high', 'xhigh', 'max')
DEFAULT_URL = 'https://ai.axurion.com.br/v1'
DEFAULT_MODEL = 'astra-coding'
PROFILE = 'axurion'
PROVIDER = 'axurion_gateway'

class CLIError(Exception):
    pass

class HTTPError(CLIError):
    def __init__(self, status):
        self.status = status
        super().__init__(f'HTTP {status}: ' + {401:'chave ausente ou inválida',403:'acesso negado',404:'endpoint ou modelo não encontrado',409:'conflito de estado/sessão',429:'limite de utilização',500:'erro no servidor',502:'gateway indisponível',503:'serviço indisponível'}.get(status,'requisição recusada'))

def app_home():
    return Path(os.environ.get('AXURION_HOME') or (Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Axurion' if os.name == 'nt' else Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home()/'.config'))) / 'axurion')).expanduser().resolve()

def codex_home():
    return Path(os.environ.get('CODEX_HOME') or Path.home()/'.codex').expanduser().resolve()

def private_dir(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if os.name != 'nt':
        path.chmod(0o700)

def atomic(path, content, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.axurion-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(content if isinstance(content, bytes) else content.encode('utf-8'))
            f.flush()
            os.fsync(f.fileno())
        if os.name != 'nt': os.chmod(tmp, mode)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)

def normalize_url(raw):
    try:
        p = urlsplit(raw.strip()); _ = p.port
    except ValueError as e:
        raise CLIError('URL inválida.') from e
    if p.scheme not in ('http','https') or not p.hostname or p.username or p.password or p.query or p.fragment or any(c.isspace() or ord(c)<32 for c in raw.strip()):
        raise CLIError('Informe URL HTTP(S), sem usuário, senha, query ou fragmento.')
    if p.scheme == 'http':
        try: local = ipaddress.ip_address(p.hostname).is_loopback
        except ValueError: local = p.hostname.lower() == 'localhost'
        if not local: raise CLIError('HTTP é permitido somente em loopback. Use HTTPS para acesso remoto autorizado.')
    return urlunsplit((p.scheme,p.netloc,p.path.rstrip('/') or '/v1','',''))

def valid_key(key):
    if not key or any(ord(c)<33 or ord(c)>126 for c in key):
        raise CLIError('API Key inválida: informe um token ASCII sem espaços.')
    return key

def valid_model(model):
    if not re.fullmatch(r'[A-Za-z0-9_.:/-]{1,200}', model): raise CLIError('ID de modelo inválido.')
    return model

def config(home):
    try: c = json.loads((home/'config.json').read_text(encoding='utf-8'))
    except FileNotFoundError: raise CLIError('Gateway não configurado. Execute axurion setup.') from None
    except (ValueError, OSError): raise CLIError('Configuração local inválida.') from None
    if not isinstance(c,dict) or c.get('storage') not in ('keyring','file','env') or not isinstance(c.get('base_url'),str) or not isinstance(c.get('model'),str) or c.get('effort') not in EFFORTS: raise CLIError('Configuração local inválida.')
    if c.get('default_harness', 'opencode') not in HARNESSES: raise CLIError('Harness padrão inválido.')
    c['base_url']=normalize_url(c['base_url']); valid_model(c['model'])
    return c

def save_config(home,c):
    private_dir(home); atomic(home/'config.json',json.dumps(c,indent=2,ensure_ascii=False)+'\n')

def keyring_backend():
    try:
        import keyring
        b=keyring.get_keyring()
        # Only known OS-backed implementations, not plaintext/third-party backends.
        if type(b).__module__ not in ('keyring.backends.macOS','keyring.backends.Windows','keyring.backends.SecretService','keyring.backends.kwallet','keyring.backends.libsecret'):
            return None
        if b.priority <= 0: return None
        return keyring
    except Exception: return None

def account(home): return str(home.resolve())

def store_key(home, storage, key):
    valid_key(key); private_dir(home)
    if storage=='file': atomic(home/'gateway.key',key)
    elif storage=='keyring':
        k=keyring_backend()
        if not k: raise CLIError('Cofre do sistema indisponível. Instale keyring ou selecione armazenamento explicitamente.')
        try: k.set_password(SERVICE,account(home),key)
        except Exception: raise CLIError('Não foi possível gravar no cofre do sistema.') from None
    elif storage=='env': raise CLIError('Modo env: forneça AXURION_API_KEY no ambiente; não gravamos a chave.')

def get_key(home,c):
    env=os.environ.get('AXURION_API_KEY')
    if env: return valid_key(env)
    if c['storage']=='env': raise CLIError('AXURION_API_KEY não está no ambiente.')
    if c['storage']=='file':
        try: return valid_key((home/'gateway.key').read_text(encoding='utf-8').strip())
        except FileNotFoundError: raise CLIError('Chave ausente. Execute axurion login.') from None
    k=keyring_backend()
    if not k: raise CLIError('Cofre do sistema indisponível neste ambiente Python.')
    try: key=k.get_password(SERVICE,account(home))
    except Exception: raise CLIError('Não foi possível ler o cofre do sistema.') from None
    if not key: raise CLIError('Chave ausente. Execute axurion login.')
    return valid_key(key)

def remove_key(home,storage):
    if storage=='file': (home/'gateway.key').unlink(missing_ok=True)
    elif storage=='keyring':
        k=keyring_backend()
        if not k: raise CLIError('Cofre indisponível; não foi possível remover a chave.')
        try:
            if k.get_password(SERVICE,account(home)): k.delete_password(SERVICE,account(home))
        except Exception: raise CLIError('Não foi possível remover a chave do cofre.') from None

def secret_prompt(label='API Key: '):
    if not sys.stdin.isatty(): raise CLIError('Use um terminal interativo para digitar a chave, ou o modo env.')
    with warnings.catch_warnings():
        warnings.simplefilter('error',getpass.GetPassWarning)
        try: return valid_key(getpass.getpass(label).strip())
        except getpass.GetPassWarning: raise CLIError('Terminal não consegue ocultar a chave.') from None

def archive_path():
    p=Path(sys.argv[0]).resolve()
    return p if p.is_file() and zipfile.is_zipfile(p) else None

def launcher_bin(home):
    return home/'bin' if os.name=='nt' else Path.home()/'.local/bin'

def install_archive(home, source=None):
    src=Path(source).expanduser().resolve() if source else archive_path()
    if not src: raise CLIError('Use a distribuição gateway-cli.pyz para instalar/atualizar.')
    try:
        with zipfile.ZipFile(src) as z:
            if z.testzip() is not None or not {'__main__.py','gateway_cli/cli.py','gateway_cli/__init__.py'}.issubset(z.namelist()): raise CLIError('Pacote Axurion inválido.')
    except (OSError,zipfile.BadZipFile): raise CLIError('Pacote Axurion inválido.') from None
    private_dir(home); target=home/'gateway-cli.pyz'
    bindir=launcher_bin(home); bindir.mkdir(parents=True,exist_ok=True)
    if os.name=='nt':
        launch=bindir/'axurion.cmd'
        # Windows launcher uses absolute interpreter and archive paths.
        content=f'@echo off\r\nrem Managed by Axurion Gateway CLI\r\n"{sys.executable}" "{target}" --home "{home}" %*\r\n'
    else:
        import shlex
        launch=bindir/'axurion'
        content=f'#!/bin/sh\n{MARK}\nexec {shlex.quote(sys.executable)} {shlex.quote(str(target))} --home {shlex.quote(str(home))} "$@"\n'
    if launch.exists() and 'Managed by Axurion Gateway CLI' not in launch.read_text(encoding='utf-8',errors='replace'):
        raise CLIError(f'Comando existente não gerenciado: {launch}.')
    if src!=target: atomic(target,src.read_bytes())
    atomic(launch,content,0o700)
    return target,launch

def helper_args(home):
    installed=home/'gateway-cli.pyz'
    if not installed.exists() and archive_path(): install_archive(home)
    return ([str(installed)] if installed.exists() else ['-m','gateway_cli'])+['--home',str(home),'_token']

def check_profile(ch):
    base=ch/'config.toml'; p=ch/'axurion.config.toml'
    if base.exists():
        try: b=tomllib.loads(base.read_text(encoding='utf-8-sig'))
        except (ValueError,OSError): raise CLIError('config.toml principal inválido; não foi alterado.') from None
        if PROVIDER in b.get('model_providers',{}): raise CLIError(f'Provedor {PROVIDER} já existe no config.toml principal. Resolva o conflito manualmente.')
    if p.exists() and not p.read_text(encoding='utf-8').startswith((MARK,OLD_MARK)):
        raise CLIError('Perfil axurion existente não gerenciado. Preserve/renomeie-o antes de continuar.')
    return p

def write_profile(home,c,ch=None):
    ch=ch or codex_home(); p=check_profile(ch); ch.mkdir(parents=True,exist_ok=True)
    q=lambda v:json.dumps(str(v),ensure_ascii=False)
    args=', '.join(q(x) for x in helper_args(home))
    text=f'''{MARK}
model = {q(c['model'])}
model_provider = "{PROVIDER}"
model_reasoning_effort = {q(c['effort'])}
web_search = "disabled"

[model_providers.{PROVIDER}]
name = "Axurion AI Gateway"
base_url = {q(c['base_url'])}
wire_api = "responses"
supports_websockets = false

[model_providers.{PROVIDER}.auth]
command = {q(sys.executable)}
args = [{args}]
timeout_ms = 5000
refresh_interval_ms = 300000
'''
    tomllib.loads(text)
    if p.exists() and p.read_text(encoding='utf-8')!=text:
        atomic(ch/f'axurion.config.{time.time_ns()}.bak',p.read_bytes())
    atomic(p,text); return p

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl): return None

def request(c,key,path,body=None,timeout=15,session=None):
    url=c['base_url']+path
    headers={'Authorization':'Bearer '+valid_key(key),'Accept':'application/json','User-Agent':'AxurionGatewayCLI/'+__version__}
    if session: headers['X-Axurion-Session-Id']=session
    data=None
    if body is not None:
        data=json.dumps(body).encode(); headers['Content-Type']='application/json'
    req=urllib.request.Request(url,data=data,headers=headers,method='POST' if body is not None else 'GET')
    start=time.monotonic()
    try:
        # Honor platform proxy settings, validate TLS, never forward secrets through redirects.
        with urllib.request.build_opener(NoRedirect()).open(req,timeout=timeout) as r:
            raw=r.read(8*1024*1024+1)
            if len(raw)>8*1024*1024: raise CLIError('Resposta grande demais.')
            try: result=json.loads(raw)
            except ValueError: raise CLIError('Resposta não é JSON; confirme a Base URL.') from None
    except urllib.error.HTTPError as e:
        e.close(); raise HTTPError(e.code) from None
    except (urllib.error.URLError,TimeoutError,OSError): raise CLIError('Falha de conexão/TLS ou timeout. Confira URL, rede e certificado.') from None
    return result,round((time.monotonic()-start)*1000)

def model_ids(result):
    if not isinstance(result,dict) or not isinstance(result.get('data'),list): raise CLIError('Formato inesperado do catálogo de modelos.')
    return [model.id for model in parse_catalogue(result)]

def dashboard_url(c):
    p=urlsplit(c['base_url']); base=p.path.rstrip('/')
    if base.endswith('/v1'): base=base[:-3]
    return urlunsplit((p.scheme,p.netloc,base+'/v0/resource/plugins/axurion-intelligent-router/admin','',''))

def summarize_server_usage(result):
    # API-key identifiers may contain actual provider secrets. Never print or persist them.
    if not isinstance(result,dict): raise CLIError('Formato inesperado de uso remoto.')
    rows=[]
    for provider, entries in result.items():
        if not isinstance(entries,dict): continue
        counts=[e for e in entries.values() if isinstance(e,dict) and any(type(e.get(k)) is int for k in ('success','failed'))]
        if not counts: continue
        # Only aggregate numeric counters; no provider or credential names from the response.
        rows.append({'credentials':len(counts),'success':sum(max(0,e.get('success',0)) for e in counts if type(e.get('success')) is int),'failed':sum(max(0,e.get('failed',0)) for e in counts if type(e.get('failed')) is int)})
    if result and not rows: raise CLIError('Formato de uso remoto não reconhecido. Consulte o painel.')
    return {'scope':'Contadores de API keys reportados pelo servidor; podem não incluir OAuth, tokens ou cotas.', 'provider_groups':len(rows), 'credentials':sum(r['credentials'] for r in rows), 'success':sum(r['success'] for r in rows), 'failed':sum(r['failed'] for r in rows)}

def server_usage(c, as_json=False):
    if not sys.stdin.isatty(): raise CLIError('Uso remoto exige uma chave administrativa digitada em terminal interativo.')
    key=secret_prompt('Management Key (não será armazenada): ')
    p=urlsplit(c['base_url']); root=p.path[:-3] if p.path.endswith('/v1') else p.path
    admin_c={'base_url':urlunsplit((p.scheme,p.netloc,root,'',''))}
    try: result,_=request(admin_c,key,'/v8/management/observability/usage/api-keys')
    except HTTPError as e:
        if e.status!=404: raise
        result,_=request(admin_c,key,'/v0/management/api-key-usage')
    summary=summarize_server_usage(result)
    print(json.dumps(summary,indent=2,ensure_ascii=False) if as_json else f'{summary["scope"]}\nCredenciais: {summary["credentials"]} | Sucesso: {summary["success"]} | Falhas: {summary["failed"]}')

def choose_storage(explicit,old=None):
    if explicit: return explicit
    if old: return old
    if keyring_backend(): return 'keyring'
    if not sys.stdin.isatty(): raise CLIError('Sem cofre disponível. Escolha --storage env ou --storage file explicitamente.')
    print('Cofre do sistema indisponível. A chave pode ficar no ambiente ou em arquivo local NÃO criptografado.')
    choice=input('Armazenamento [env/file, padrão env]: ').strip().lower() or 'env'
    if choice not in ('env','file'): raise CLIError('Escolha env ou file.')
    return choice

def offer_harness_install(adapter):
    if adapter.detect(): return True
    packages = {'opencode': '@opencode/cli', 'codex': '@openai/codex',
                'pi': '@earendil-works/pi-coding-agent', 'claude': '@anthropic-ai/claude-code@latest'}
    npm = shutil.which('npm')
    print(f'{adapter.display_name} não encontrado. Instalação oficial via npm: {packages[adapter.name]}')
    if not npm or not sys.stdin.isatty():
        print('Instale-o manualmente usando a documentação oficial; nenhuma instalação foi iniciada.')
        return False
    if input('Instalar globalmente com npm? [s/N] ').strip().lower() not in ('s','sim','y','yes'): return False
    command=[npm,'install','-g']
    if adapter.name == 'pi': command.append('--ignore-scripts')
    command.append(packages[adapter.name])
    if subprocess.call(command): raise CLIError(f'Falha ao instalar {adapter.display_name}.')
    if not adapter.detect(): print('Instalação concluída; verifique se o diretório global do npm está no PATH.')
    return bool(adapter.detect())

def setup(home,args):
    old=config(home) if (home/'config.json').exists() else None
    raw=args.url or (input(f'Base URL [{old["base_url"] if old else DEFAULT_URL}]: ').strip() or (old['base_url'] if old else DEFAULT_URL))
    c={'base_url':normalize_url(raw),'model':valid_model(args.model or (old['model'] if old else DEFAULT_MODEL)), 'effort':args.effort or (old['effort'] if old else 'medium'), 'storage':choose_storage(args.storage,old['storage'] if old else None)}
    if old and 'default_harness' in old: c['default_harness']=old['default_harness']
    if c['storage']=='env':
        print('Modo env: defina AXURION_API_KEY no ambiente antes de usar o gateway.')
    else:
        if c['storage']=='file': print('Aviso: chave local NÃO criptografada; protegida pelas permissões do usuário.')
        store_key(home,c['storage'],secret_prompt())
    save_config(home,c)
    try: p=write_profile(home,c)
    except (CLIError, OSError) as e:
        p='não configurado'
        print(f'Codex não configurado: {e}. As demais integrações continuam disponíveis.',file=sys.stderr)
    if old and old['storage']!=c['storage']:
        try: remove_key(home,old['storage'])
        except CLIError as e: print('Aviso: remova a credencial antiga manualmente: '+str(e),file=sys.stderr)
    print(f'Perfil: {p}\nModelo: {c["model"]} ({c["effort"]})\nNenhuma inferência realizada.')
    if sys.stdin.isatty():
        print('Harnesses disponíveis:')
        for adapter in HARNESSES.values(): print(f'  {adapter.display_name}: {"instalado" if adapter.detect() else "não instalado"}')
        if not HARNESSES['opencode'].detect(): offer_harness_install(HARNESSES['opencode'])
        print(f'Harness padrão: {c.get("default_harness", "opencode")} | Modelo: {c["model"]} | Reasoning: {c["effort"]}')
        if input('Configurar OpenCode e os demais harnesses instalados? [S/n] ').strip().lower() in ('', 's', 'sim', 'y', 'yes'):
            models = None
            for name, adapter in HARNESSES.items():
                if name == 'codex' or (name != 'opencode' and not adapter.detect()): continue
                try:
                    if name in ('opencode', 'pi') and models is None:
                        models=parse_catalogue(request(c,get_key(home,c),'/models')[0])
                    adapter.sync(home,c,models or [],atomic)
                    print(f'{adapter.display_name}: integração configurada.')
                except (CLIError, ValueError, OSError) as e:
                    print(f'{adapter.display_name} não configurado: {e}. Execute axurion sync {name} mais tarde.',file=sys.stderr)
    else: print('Execute axurion sync opencode para configurar o harness padrão.')

def append_usage(home,c,result,ms,model,effort):
    u=result.get('usage') or {}; row={'time':int(time.time()),'gateway':c['base_url'],'model':model,'effort':effort,'latency_ms':ms}
    for k in ('prompt_tokens','completion_tokens','total_tokens','input_tokens','output_tokens'):
        if isinstance(u.get(k),int) and u[k]>=0: row[k]=u[k]
    private_dir(home)
    p=home/'probe-usage.jsonl'; fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    with os.fdopen(fd,'a',encoding='utf-8') as f: f.write(json.dumps(row)+'\n')

def show_usage(home,c,as_json=False):
    p=home/'probe-usage.jsonl'; rows=[]
    if p.exists():
        for line in p.read_text(encoding='utf-8').splitlines():
            try:
                r=json.loads(line)
                if r.get('gateway')==c['base_url']: rows.append(r)
            except (ValueError,AttributeError): pass
    summary={'scope':'Somente testes de inferência feitos por esta CLI; não inclui Codex/Orca ou cotas remotas.', 'requests':len(rows),'total_tokens_reported':sum(r.get('total_tokens',0) for r in rows),'dashboard':dashboard_url(c)}
    print(json.dumps(summary,ensure_ascii=False,indent=2) if as_json else f'{summary["scope"]}\nTestes: {summary["requests"]}\nTokens reportados: {summary["total_tokens_reported"]}\nUso global: {summary["dashboard"]}')

def build_parser():
    p=argparse.ArgumentParser(prog='axurion',description='Axurion Gateway CLI — um perfil, vários modelos.')
    p.add_argument('--version',action='version',version=__version__); p.add_argument('--home',type=Path,help=argparse.SUPPRESS)
    p.add_argument('--model'); p.add_argument('--effort',choices=EFFORTS)
    p.add_argument('--yolo',action='store_true',help='Ativar aprovações automáticas nativas somente nesta sessão (reduz proteções).')
    sp=p.add_subparsers(dest='cmd')
    s=sp.add_parser('setup',help='Configurar URL, chave e perfil Codex'); s.add_argument('--url'); s.add_argument('--model'); s.add_argument('--effort',choices=EFFORTS); s.add_argument('--storage',choices=('keyring','file','env'))
    s=sp.add_parser('install',help='Instalar launcher ou integrar harness'); s.add_argument('harness',nargs='?',choices=tuple(HARNESSES)); s.add_argument('--all',action='store_true'); s.add_argument('--setup',action='store_true'); s.add_argument('--storage',choices=('keyring','file','env'))
    s=sp.add_parser('default',help='Mostrar ou alterar harness padrão'); s.add_argument('harness',nargs='?',choices=tuple(HARNESSES))
    sp.add_parser('harnesses',help='Detectar harnesses no PATH')
    for command in ('sync', 'uninstall'):
        s=sp.add_parser(command); s.add_argument('harness',nargs='?',choices=tuple(HARNESSES))
    for name in ('opencode', 'pi', 'claude'):
        s=sp.add_parser(name); s.add_argument('--model',default=argparse.SUPPRESS); s.add_argument('--effort',choices=EFFORTS,default=argparse.SUPPRESS); s.add_argument('--yolo',action='store_true',default=argparse.SUPPRESS,help='Ativar aprovações automáticas nativas nesta sessão.'); s.add_argument('args',nargs=argparse.REMAINDER)
    sp.add_parser('login',help='Cadastrar ou trocar chave local'); sp.add_parser('logout',help='Remover chave armazenada'); sp.add_parser('config',help='Mostrar configuração sem segredos'); sp.add_parser('doctor',help='Diagnóstico local sem rede').add_argument('harness',nargs='?',choices=tuple(HARNESSES)); sp.add_parser('dashboard',help='Abrir painel do gateway'); sp.add_parser('profile',help='Recriar perfil Codex gerenciado'); sp.add_parser('_token',help=argparse.SUPPRESS)
    for name in ('models','status','usage'):
        s=sp.add_parser(name,help={'models':'Listar modelos sem inferência','status':'Testar autenticação/conectividade sem inferência','usage':'Mostrar consumo local e link do painel'}[name]); s.add_argument('--json',action='store_true')
        if name=='usage': s.add_argument('--server',action='store_true',help='Consultar contadores remotos com management key (opcional)')
    s=sp.add_parser('test',help='Teste de inferência explícito (consome cota)'); s.add_argument('--model'); s.add_argument('--effort',choices=EFFORTS); s.add_argument('--yes',action='store_true'); s.add_argument('--protocol',choices=('chat','responses'),default='responses')
    s=sp.add_parser('codex',help='Abrir Codex com perfil Axurion'); s.add_argument('--effort',choices=EFFORTS,default=argparse.SUPPRESS); s.add_argument('--model',default=argparse.SUPPRESS); s.add_argument('--yolo',action='store_true',default=argparse.SUPPRESS,help='Ativar aprovações automáticas nativas nesta sessão.'); s.add_argument('args',nargs=argparse.REMAINDER)
    s=sp.add_parser('update',help='Atualizar a CLI'); s.add_argument('package',type=Path,nargs='?')
    g=s.add_mutually_exclusive_group(); g.add_argument('--check',action='store_true'); g.add_argument('--beta',action='store_true'); g.add_argument('--version',dest='tag'); g.add_argument('--rollback',action='store_true')
    sp.add_parser('_update_check',help=argparse.SUPPRESS)
    return p

def main(argv=None):
    args=build_parser().parse_args(argv); home=(args.home or app_home()).expanduser().resolve()
    try:
        if args.cmd=='_update_check':
            updater.background_worker(home,__version__,atomic); return 0
        if args.cmd not in ('update','_token'): updater.background(home,__version__,atomic)
        if args.cmd=='install' and not args.harness and not args.all:
            _,launch=install_archive(home); print(f'Comando instalado: {launch}\nSe necessário, adicione {launch.parent} ao PATH do usuário.')
            if args.setup: setup(home,argparse.Namespace(url=None,model=None,effort=None,storage=args.storage))
            return 0
        if args.cmd=='update':
            if args.package and (args.check or args.beta or args.tag or args.rollback): raise CLIError('Pacote local não pode ser combinado com opções de atualização.')
            state=updater.read_state(home); target=home/'gateway-cli.pyz'; backup=home/'gateway-cli.pyz.bak'
            if args.rollback:
                if not backup.is_file(): raise CLIError('Nenhuma versão anterior disponível.')
                data=backup.read_bytes()
            elif args.package:
                data=args.package.expanduser().read_bytes()
            else:
                selected='beta' if args.beta else updater.effective_channel(state,__version__)
                release=updater.select_release(updater.releases(),selected,args.tag)
                tag=release['tag_name']
                if args.check:
                    print(f'Atualização disponível: {tag}' if updater.version_key(tag)>updater.version_key(__version__) else f'CLI atualizada ({__version__}).'); return 0
                if not args.tag and updater.version_key(tag)<=updater.version_key(__version__):
                    print(f'CLI atualizada ({__version__}); nenhum downgrade automático.'); return 0
                data=updater.package(release)
            private_dir(home)
            with tempfile.TemporaryDirectory(dir=home) as directory:
                candidate=Path(directory)/'gateway-cli.pyz'; candidate.write_bytes(data)
                previous=target.read_bytes() if target.exists() else None
                try:
                    with zipfile.ZipFile(candidate) as z:
                        if z.testzip() is not None or not {'__main__.py','gateway_cli/cli.py','gateway_cli/__init__.py'}.issubset(z.namelist()): raise CLIError('Pacote Axurion inválido.')
                except (OSError,zipfile.BadZipFile): raise CLIError('Pacote Axurion inválido.') from None
                # Keep the last working archive before replacing it.
                if previous is not None: atomic(backup,previous)
                try: _,launch=install_archive(home,candidate)
                except Exception:
                    if previous is not None: atomic(target,previous)
                    raise
            if not args.package and not args.rollback: state['channel']=updater.channel(tag)
            else:
                with zipfile.ZipFile(target) as z:
                    match=re.search(r"__version__\s*=\s*['\"]([^'\"]+)",z.read('gateway_cli/__init__.py').decode('utf-8'))
                    if match: state['channel']=updater.channel(match.group(1))
            state.pop('available',None); state.pop('checked_at',None); atomic(home/'update.json',json.dumps(state,indent=2))
            print(f'Pacote atualizado: {launch}'); return 0
        if args.cmd=='setup': setup(home,args); return 0
        if args.cmd=='doctor':
            print(f'Python: {sys.version.split()[0]}\nConfiguração: {home}\nCofre disponível: {"sim" if keyring_backend() else "não"}')
            for name, adapter in HARNESSES.items():
                if args.harness and name != args.harness: continue
                configured = (codex_home()/'axurion.config.toml').is_file() if name == 'codex' else adapter.configured(home)
                print(f'{adapter.display_name}: {adapter.detect() or "não encontrado"}; integração: {"configurada" if configured else "ausente"}')
            if not (home/'config.json').exists(): print('Execute axurion setup.'); return 0
            c=config(home); print(f'URL: {c["base_url"]}\nPerfil: {codex_home()/"axurion.config.toml"}')
            try: get_key(home,c); print('Chave: disponível')
            except CLIError: print('Chave: indisponível'); return 1
            return 0
        if args.cmd=='harnesses':
            for harness in HARNESSES.values():
                configured = ((codex_home()/'axurion.config.toml').is_file() if harness.name == 'codex' else harness.configured(home))
                print(f'{harness.display_name}: {harness.detect() or "não encontrado"} | integração: {"configurada" if configured else "não configurada"}')
            return 0
        c=config(home)
        if args.cmd=='default':
            if args.harness:
                c['default_harness']=args.harness; save_config(home,c)
            print(c.get('default_harness','opencode'))
            return 0
        if args.cmd=='_token': sys.stdout.write(get_key(home,c)); return 0
        if args.cmd=='config': print(json.dumps(c,indent=2,ensure_ascii=False)); return 0
        if args.cmd=='profile': print(write_profile(home,c)); return 0
        if args.cmd=='login':
            if c['storage']=='env': raise CLIError('Modo env: atualize AXURION_API_KEY no ambiente, ou reconfigure o armazenamento.')
            store_key(home,c['storage'],secret_prompt()); print('Chave atualizada.'); return 0
        if args.cmd=='logout':
            remove_key(home,c['storage']); print('Credencial armazenada removida. Limpe AXURION_API_KEY do ambiente se estiver definida. O token remoto não foi revogado.'); return 0
        if args.cmd=='dashboard':
            url=dashboard_url(c); print(url); webbrowser.open(url); return 0
        if args.cmd=='usage':
            if args.server: server_usage(c,args.json)
            else: show_usage(home,c,args.json)
            return 0
        if args.cmd in ('install', 'sync', 'uninstall'):
            names = ([args.harness] if args.harness else list(HARNESSES))
            if args.cmd == 'uninstall' and not args.harness:
                raise CLIError('Informe o harness a remover.')
            models = None
            catalogue_error = None
            if args.cmd != 'uninstall' and any(n in ('opencode', 'pi') for n in names):
                try:
                    result,_ = request(c,get_key(home,c),'/models')
                    models = parse_catalogue(result)
                    if not models: raise CLIError('Catálogo vazio.')
                except (CLIError, OSError, ValueError) as e:
                    catalogue_error = str(e)
            failed = False
            for name in names:
                adapter = HARNESSES[name]
                try:
                    if catalogue_error and name in ('opencode', 'pi') and args.cmd != 'uninstall':
                        raise CLIError(f'Catálogo indisponível: {catalogue_error}')
                    if args.cmd == 'uninstall':
                        if name == 'codex':
                            profile=codex_home()/'axurion.config.toml'
                            if profile.exists():
                                if not profile.read_text(encoding='utf-8').startswith((MARK, OLD_MARK)): raise CLIError('Perfil Codex não gerenciado.')
                                atomic(profile.with_name(f'axurion.config.{time.time_ns()}.bak'),profile.read_bytes()); profile.unlink()
                        else: adapter.uninstall(home,atomic)
                    elif name == 'codex': write_profile(home,c)
                    else: adapter.sync(home,c,models or [],atomic)
                    print(f'{adapter.display_name}: integração {"removida" if args.cmd == "uninstall" else "configurada"}.')
                    if args.cmd == 'install' and not adapter.detect(): offer_harness_install(adapter)
                    elif not adapter.detect() and args.cmd != 'uninstall': print(f'{adapter.display_name}: executável não encontrado.')
                except (CLIError, OSError, ValueError) as e:
                    failed=True; print(f'{adapter.display_name}: {e}',file=sys.stderr)
            return int(failed)
        selected = args.cmd or c.get('default_harness','opencode')
        if selected in ('opencode','pi','claude','codex'):
            rest=list(getattr(args,'args',[]))
            # REMAINDER captures options after a native positional argument (e.g. resume).
            boundary=rest.index('--') if '--' in rest else len(rest)
            before=rest[:boundary]; yolo=args.yolo or '--yolo' in before
            rest=[x for x in before if x != '--yolo'] + rest[boundary:]
            if rest[:1]==['--']: rest=rest[1:]
            if yolo and selected=='pi': raise CLIError('Pi: --yolo não é suportado; não há opção nativa equivalente verificada.')
            flags={'opencode':'--auto','codex':'--dangerously-bypass-approvals-and-sandbox','claude':'--dangerously-skip-permissions'}
            if yolo:
                flag=flags[selected]
                if flag not in rest: rest.insert(0,flag)
        if selected in ('opencode','pi','claude'):
            adapter=HARNESSES[selected]; exe=adapter.detect()
            if not exe:
                offer_harness_install(adapter)
                exe=adapter.detect()
                if not exe: raise CLIError(f'{adapter.display_name} não encontrado; nenhum outro harness foi iniciado.')
            model=valid_model(args.model or c['model']); effort=args.effort or c['effort']
            if selected == 'pi':
                if args.effort: raise CLIError('Pi: níveis de reasoning não foram verificados; omita --effort para iniciar sem thinking.')
                print('Pi: thinking desativado; roteamento por effort não está verificado.', file=sys.stderr)
                command=[exe,'--provider','axurion','--model',model,'--thinking','off',*rest]
            elif selected == 'claude':
                if not model.lower().startswith('claude-'): raise CLIError('Claude Code exige um ID de modelo Claude explícito; compatibilidade do gateway não verificada.')
                command=adapter.command(exe,model,effort,rest)
            else: command=adapter.command(exe,model,effort,rest)
            if not adapter.configured(home):
                if not sys.stdin.isatty() or input(f'Configurar integração {adapter.display_name} agora? [S/n] ').strip().lower() not in ('', 's', 'sim', 'y', 'yes'):
                    raise CLIError(f'Integração não configurada. Execute axurion install {selected}.')
                models = []
                if selected in ('opencode', 'pi'):
                    models=parse_catalogue(request(c,get_key(home,c),'/models')[0])
                adapter.sync(home,c,models,atomic)
                if not adapter.configured(home): raise CLIError('Integração não pôde ser configurada.')
            env=os.environ.copy(); key=get_key(home,c)
            if selected == 'claude':
                env['ANTHROPIC_BASE_URL']=adapter.base_url(c['base_url']); env['ANTHROPIC_AUTH_TOKEN']=key
                env.pop('ANTHROPIC_API_KEY',None)
            else: env['AXURION_API_KEY']=key

            if selected == 'opencode':
                overrides = json.loads(
                    env.get('OPENCODE_CONFIG_CONTENT') or '{}'
                )

                overrides['model'] = f'axurion/{model}'

                model_config = (
                    overrides
                    .setdefault('providers', {})
                    .setdefault('axurion', {})
                    .setdefault('models', {})
                    .setdefault(model, {})
                )

                model_config.setdefault('body', {})[
                    'reasoning_effort'
                ] = effort

                env['OPENCODE_CONFIG_CONTENT'] = json.dumps(overrides)
            if yolo:
                detail={'opencode':'permissões não negadas explicitamente serão aprovadas automaticamente', 'claude':'verificações de permissão serão ignoradas'}[selected]
                print(f'Aviso: YOLO ativo — {detail}; políticas e restrições externas permanecem aplicáveis.',file=sys.stderr)
            return subprocess.call(command,env=env)
        key=get_key(home,c)
        if selected=='codex':
            exe=shutil.which('codex')
            if not exe: raise CLIError('Codex CLI não encontrado no PATH.')
            effort=args.effort or c['effort']
            # Prevent accidental alternate profile/provider overrides by normal options; advanced Codex flags are user's responsibility.
            if not (codex_home()/'axurion.config.toml').exists(): write_profile(home,c)
            if yolo: print('Aviso: YOLO ativo — aprovações e sandbox do Codex desabilitados; restrições externas permanecem aplicáveis.',file=sys.stderr)
            return subprocess.call([exe,'--profile','axurion','-c',f'model_reasoning_effort="{effort}"','-m',valid_model(args.model or c['model']),*rest])
        if args.cmd in ('models','status'):
            result,ms=request(c,key,'/models'); ids=model_ids(result)
            data={'status':'ok','latency_ms':ms,'models':ids,'configured_model_available':c['model'] in ids}
            if args.json: print(json.dumps(data,indent=2,ensure_ascii=False))
            elif args.cmd=='models': print('\n'.join(ids) or '(nenhum modelo)')
            else: print(f'Gateway acessível ({ms} ms). {len(ids)} modelos. Modelo configurado listado: {data["configured_model_available"]}. Nenhuma inferência realizada.')
            return 0
        if args.cmd=='test':
            model=valid_model(args.model or c['model']); effort=args.effort or c['effort']
            if not args.yes:
                if not sys.stdin.isatty() or input(f'Enviar teste de inferência ({model}, {effort})? [s/N] ').strip().lower() not in ('s','sim','y','yes'): print('Cancelado. Nenhuma inferência.'); return 0
            if args.protocol=='chat':
                path='/chat/completions'; body={'model':model,'reasoning_effort':effort,'messages':[{'role':'user','content':'Responda apenas OK.'}],'stream':False}
            else:
                path='/responses'; body={'model':model,'reasoning':{'effort':effort},'input':'Responda apenas OK.','stream':False,'store':False}
            result,ms=request(c,key,path,body,60,'axurion-probe-'+uuid.uuid4().hex)
            if not isinstance(result,dict) or result.get('error'): raise CLIError('Resposta de inferência inesperada.')
            append_usage(home,c,result,ms,model,effort)
            # Never print request headers or raw responses.
            u=result.get('usage') or {}; print(f'Inferência respondeu ({ms} ms); modelo virtual: {model}; reasoning: {effort}; tokens reportados: {u.get("total_tokens","indisponível")}. Confira modelo real no painel.')
            return 0
        return 2
    except (CLIError,OSError,ValueError,urllib.error.URLError) as e:
        print(f'Erro: {e}',file=sys.stderr); return 1
    except (KeyboardInterrupt,EOFError): print('\nCancelado.',file=sys.stderr); return 130
