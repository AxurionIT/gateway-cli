"""Validated, secret-free model catalogue snapshots.

A catalogue entry is not proof of protocol or capability support. Keep the
server's metadata intact instead of fabricating context limits or reasoning.
"""
from dataclasses import dataclass
import re

_MODEL_ID = re.compile(r'[A-Za-z0-9_.:/-]{1,200}\Z')

@dataclass(frozen=True)
class Model:
    id: str
    metadata: dict


def parse_catalogue(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
        raise ValueError('Formato inesperado do catálogo de modelos.')
    models = {}
    for item in payload['data']:
        if not isinstance(item, dict):
            continue
        model_id = item.get('id')
        if not isinstance(model_id, str) or not _MODEL_ID.fullmatch(model_id):
            continue
        # Only retain publicly useful, explicit capability metadata. Never cache
        # arbitrary server fields, which could contain credentials or identifiers.
        metadata = {k: item[k] for k in ('context_window', 'max_output_tokens', 'capabilities') if k in item}
        models[model_id] = Model(model_id, metadata)
    return [models[k] for k in sorted(models)]
