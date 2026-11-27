"""Safely manage one named JSON provider without taking ownership of a file."""
import hashlib
import json
import time
from . import jsonc
from pathlib import Path


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read_json(path):
    if not path.exists(): return {}
    obj = jsonc.loads(path.read_text(encoding='utf-8-sig')) if path.suffix == '.jsonc' else json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(obj, dict): raise ValueError(f'Configuração não é um objeto JSON: {path}')
    return obj


def update_provider(path, state_path, section, provider, atomic, remove=False):
    """Reject unmanaged/conflicted entries; update only a previously owned entry.

    A separate ownership receipt prevents replacing or removing user edits.
    Config is backed up before each modification. A crash after config write but
    before receipt write may require manual recovery, never silent overwrite.
    """
    path, state_path = Path(path), Path(state_path)
    doc, state = read_json(path), read_json(state_path)
    entries = doc.get(section, {})
    if not isinstance(entries, dict): raise ValueError(f'Seção {section} inválida: {path}')
    current = entries.get('axurion')
    prior = state.get('digest')
    if current is not None and (not prior or digest(current) not in (prior, state.get('previous_digest'))):
        raise ValueError(f'Provedor axurion não gerenciado ou modificado em {path}; nenhuma alteração aplicada.')
    if remove:
        if current is None:
            state_path.unlink(missing_ok=True)
            return
        del entries['axurion']
    else:
        if current == provider: return
        entries['axurion'] = provider
    doc[section] = entries
    source = path.read_text(encoding='utf-8') if path.exists() else '{}'
    output = jsonc.edit(source, section, provider, remove)
    # Validate before changing either receipt or file, retaining strict JSON rules.
    if path.suffix == '.jsonc': jsonc.loads(output)
    else: json.loads(output.lstrip('\ufeff'))
    if path.exists(): atomic(path.with_name(path.name + f'.axurion.{time.time_ns()}.bak'), path.read_bytes())
    # A pending receipt recognizes both old and new states after interruption.
    # Never use it to overwrite anything except those exact known states.
    if not remove:
        atomic(state_path, json.dumps({'digest': digest(provider), 'previous_digest': prior}) + '\n')
    atomic(path, output)
    if remove: state_path.unlink(missing_ok=True)
    else: atomic(state_path, json.dumps({'digest': digest(provider)}) + '\n')
