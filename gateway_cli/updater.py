"""GitHub release discovery and non-interactive update checks."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.request

API = 'https://api.github.com/repos/AxurionIT/gateway-cli/releases'
INTERVAL = 86400
VERSION = re.compile(r'^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?$')

def version_key(tag):
    m = VERSION.fullmatch(tag)
    if not m: raise ValueError('Tag de versão inválida.')
    pre = m.group(4)
    parts = tuple((0, int(p)) if p.isdigit() else (1, p) for p in pre.split('.')) if pre else ()
    return (int(m[1]), int(m[2]), int(m[3]), 0 if pre else 1, parts)

def channel(version):
    return 'beta' if VERSION.fullmatch(version) and VERSION.fullmatch(version).group(4) else 'stable'

def read_state(home):
    try:
        state = json.loads((home/'update.json').read_text(encoding='utf-8'))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError): return {}

def fetch(url, limit=10_000_000):
    req = urllib.request.Request(url, headers={'User-Agent':'Axurion-Gateway-CLI', 'Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=5) as response:
        data = response.read(limit+1)
    if len(data)>limit: raise ValueError('Resposta de atualização muito grande.')
    return data

def releases():
    result=[]; url=API+'?per_page=100&page={}'
    for page in range(1, 11):
        data=json.loads(fetch(url.format(page), 2_000_000))
        if not isinstance(data,list): raise ValueError('Resposta de releases inválida.')
        result.extend(data)
        if len(data)<100: break
    return result

def select_release(items, selected_channel, tag=None):
    candidates=[]
    if tag: version_key(tag)
    for release in items:
        if not isinstance(release,dict) or release.get('draft'): continue
        name=release.get('tag_name')
        if not isinstance(name,str): continue
        try: key=version_key(name)
        except ValueError: continue
        if tag and name != tag: continue
        if not tag and selected_channel=='stable' and (release.get('prerelease') or channel(name)=='beta'): continue
        if not tag and selected_channel=='beta' and not release.get('prerelease'): continue
        candidates.append((key,release))
    if not candidates: raise ValueError('Nenhuma release correspondente encontrada.')
    return max(candidates,key=lambda x:x[0])[1]

def package(release):
    assets={a.get('name'):a.get('browser_download_url') for a in release.get('assets',[]) if isinstance(a,dict)}
    # Construct canonical URLs instead of trusting API-provided download destinations.
    tag=release['tag_name']; version_key(tag)
    from urllib.parse import quote
    base='https://github.com/AxurionIT/gateway-cli/releases/download/'+quote(tag,safe='')+'/'
    if not all(assets.get(n) for n in ('gateway-cli.pyz','gateway-cli.pyz.sha256')): raise ValueError('Release sem pacote ou checksum.')
    payload=fetch(base+'gateway-cli.pyz')
    checksum=fetch(base+'gateway-cli.pyz.sha256',4096).decode('ascii').strip().split()
    if not checksum or not re.fullmatch(r'[a-fA-F0-9]{64}',checksum[0]) or hashlib.sha256(payload).hexdigest()!=checksum[0].lower(): raise ValueError('SHA-256 inválido: atualização interrompida.')
    return payload

def effective_channel(state, current):
    return state.get('channel') if state.get('channel') in ('stable','beta') else channel(current)

def background(home, current, atomic):
    state=read_state(home)
    if state.get('auto_check',True) is False or os.environ.get('AXURION_NO_UPDATE_CHECK')=='1': return
    cached=state.get('available')
    try:
        if cached and version_key(cached)>version_key(current):
            print(f'Atualização disponível: {cached}. Execute axurion update.',file=sys.stderr)
    except (ValueError,TypeError): pass
    try:
        home.mkdir(parents=True,exist_ok=True)
        lock=home/'update-check.lock'
        try: lock.mkdir()
        except FileExistsError:
            if time.time()-lock.stat().st_mtime < 60: return
            lock.rmdir(); lock.mkdir()
        try:
            state=read_state(home)
            if time.time()-float(state.get('checked_at',0)) < INTERVAL: return
            state['checked_at']=time.time(); atomic(home/'update.json',json.dumps(state))
            cmd=[sys.executable]
            archive=home/'gateway-cli.pyz'
            cmd += [str(archive)] if archive.is_file() else ['-m','gateway_cli']
            cmd += ['--home',str(home),'_update_check']
            kw={'stdin':subprocess.DEVNULL,'stdout':subprocess.DEVNULL,'stderr':subprocess.DEVNULL,'close_fds':True}
            if os.name=='nt': kw['creationflags']=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            else: kw['start_new_session']=True
            subprocess.Popen(cmd,**kw)
        finally: lock.rmdir()
    except (OSError,ValueError,TypeError): pass

def background_worker(home,current,atomic):
    try:
        state=read_state(home); ch=effective_channel(state,current)
        release=select_release(releases(),ch)
        # Reload to avoid clobbering settings changed while the request was in flight.
        state=read_state(home)
        if effective_channel(state,current)==ch:
            state['available']=release['tag_name'] if version_key(release['tag_name'])>version_key(current) else None
            atomic(home/'update.json',json.dumps(state))
    except Exception: pass
