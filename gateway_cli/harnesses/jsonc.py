"""Token-aware JSONC reader/editor, preserving untouched source text."""
import json

class Parser:
    def __init__(self, text): self.s, self.i = text, 0
    def ws(self):
        s = self.s
        while self.i < len(s):
            if s[self.i].isspace(): self.i += 1
            elif s.startswith('//', self.i):
                end = s.find('\n', self.i + 2); self.i = len(s) if end < 0 else end
            elif s.startswith('/*', self.i):
                end = s.find('*/', self.i + 2)
                if end < 0: raise ValueError('Comentário JSONC não terminado')
                self.i = end + 2
            else: break
    def value(self):
        self.ws(); start = self.i
        if self.i >= len(self.s): raise ValueError('JSONC incompleto')
        c = self.s[self.i]
        if c == '{':
            self.i += 1; members = {}; self.ws()
            while self.i < len(self.s) and self.s[self.i] != '}':
                self.ws(); key_start = self.i
                key, end = json.JSONDecoder().raw_decode(self.s, self.i)
                if not isinstance(key, str): raise ValueError('Chave JSONC inválida')
                if key in members: raise ValueError('Chave JSONC duplicada: ' + key)
                self.i = end; self.ws()
                if self.i >= len(self.s) or self.s[self.i] != ':': raise ValueError('JSONC esperado :')
                self.i += 1; node = self.value(); self.ws(); comma = None
                if self.i < len(self.s) and self.s[self.i] == ',': comma = self.i; self.i += 1
                members[key] = (key_start, node, comma)
                self.ws()
                if comma is None and (self.i >= len(self.s) or self.s[self.i] != '}'): raise ValueError('JSONC esperado vírgula')
            if self.i >= len(self.s): raise ValueError('Objeto JSONC incompleto')
            self.i += 1
            return (start, self.i, {k: v[1][2] for k,v in members.items()}, members)
        if c == '[':
            self.i += 1; values = []; self.ws()
            while self.i < len(self.s) and self.s[self.i] != ']':
                values.append(self.value()[2]); self.ws(); comma = self.i < len(self.s) and self.s[self.i] == ','
                if comma: self.i += 1
                self.ws()
                if not comma and (self.i >= len(self.s) or self.s[self.i] != ']'): raise ValueError('JSONC esperado vírgula')
            if self.i >= len(self.s): raise ValueError('Array JSONC incompleto')
            self.i += 1; return (start,self.i,values,None)
        val, self.i = json.JSONDecoder().raw_decode(self.s, self.i)
        return (start,self.i,val,None)
    def parse(self):
        if self.s.startswith('\ufeff'): self.i = 1
        node = self.value(); self.ws()
        if self.i != len(self.s) or node[3] is None: raise ValueError('JSONC inválido ou raiz não é objeto')
        return node

def loads(text): return Parser(text).parse()[2]

def edit(text, section, value, remove=False):
    root = Parser(text).parse(); members = root[3]
    target = members.get(section)
    if target:
        obj = target[1]
        if obj[3] is None: raise ValueError('Seção inválida: ' + section)
    else:
        if remove: return text
        return insert(text, root, section, { 'axurion': value })
    member = obj[3].get('axurion')
    if not member:
        return text if remove else insert(text, obj, 'axurion', value)
    start, node, comma = member
    if not remove:
        # Refuse to destroy comments within an existing managed value.
        old = text[node[0]:node[1]]
        if contains_comment(old):
            if node[2] == value: return text
            raise ValueError('Comentários dentro do provider axurion exigem edição manual.')
        return text[:node[0]] + json.dumps(value, ensure_ascii=False, indent=2) + text[node[1]:]
    if contains_comment(text[start:node[1]]):
        raise ValueError('Comentários dentro do provider axurion exigem edição manual.')
    keys = list(obj[3]); idx = keys.index('axurion')
    if comma is not None: return text[:start] + text[comma+1:]
    if idx:
        prev_comma = obj[3][keys[idx-1]][2]
        return text[:prev_comma] + text[prev_comma+1:start] + text[node[1]:]
    return text[:start] + text[node[1]:]

def insert(text, obj, key, value):
    # Append immediately after the last value, leaving all comments and whitespace intact.
    members = obj[3]; encoded = json.dumps(key) + ': ' + json.dumps(value, ensure_ascii=False, indent=2)
    if members:
        last = list(members.values())[-1]; pos = last[2] + 1 if last[2] is not None else last[1][1]
        prefix = '' if last[2] is not None else ','
        return text[:pos] + prefix + '\n  ' + encoded + text[pos:]
    pos = obj[0] + 1
    return text[:pos] + '\n  ' + encoded + text[pos:]

def contains_comment(text):
    i = 0
    while i < len(text):
        if text[i] == '"':
            _, i = json.JSONDecoder().raw_decode(text, i)
        elif text.startswith('//', i) or text.startswith('/*', i): return True
        else: i += 1
    return False
