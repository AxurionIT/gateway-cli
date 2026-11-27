#!/usr/bin/env bash
# Axurion Gateway CLI bootstrap. No sudo, no policy changes.
set -euo pipefail
main() (
  VERSION='1.2.0-beta.5'
  BASE="https://github.com/AxurionIT/gateway-cli/releases/download/v${VERSION}"
  PYTHON="${PYTHON:-python3}"
  offline=false; setup=true
  for arg in "$@"; do
    case "$arg" in
      --offline) offline=true;;
      --no-setup) setup=false;;
      *) echo "Unknown option: $arg" >&2; exit 2;;
    esac
  done
  "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else "Python 3.11+ required")'
  tmp="$(mktemp -d)"
  trap 'rm -rf -- "$tmp"' EXIT
  root=''
  if [[ -n "${BASH_SOURCE[0]:-}" && -f "${BASH_SOURCE[0]}" ]]; then
    root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  fi
  if [[ -n "$root" && -f "$root/dist/gateway-cli.pyz" ]]; then
    package="$root/dist/gateway-cli.pyz"
  elif [[ -n "$root" && -f "$root/scripts/build.py" ]]; then
    "$PYTHON" "$root/scripts/build.py"
    package="$root/dist/gateway-cli.pyz"
  else
    package="$tmp/gateway-cli.pyz"
    echo "Baixando Axurion Gateway CLI v$VERSION..."
    curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --connect-timeout 15 --max-time 120 "$BASE/gateway-cli.pyz" -o "$package"
    curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' --connect-timeout 15 --max-time 120 "$BASE/gateway-cli.pyz.sha256" -o "$tmp/gateway-cli.pyz.sha256"
    "$PYTHON" - "$package" "$tmp/gateway-cli.pyz.sha256" <<'PY'
import hashlib, pathlib, re, sys
p, checksum = map(pathlib.Path, sys.argv[1:])
expected = checksum.read_text(encoding='ascii').strip().split()[0]
if not re.fullmatch(r'[a-fA-F0-9]{64}', expected) or hashlib.sha256(p.read_bytes()).hexdigest() != expected.lower():
    sys.exit('SHA-256 inválido: instalação interrompida.')
print('SHA-256 verificado.')
PY
  fi
  runtime="$PYTHON"
  if ! $offline; then
    venv="${XDG_DATA_HOME:-$HOME/.local/share}/axurion-cli/venv"
    "$PYTHON" -m venv "$venv"
    runtime="$venv/bin/python"
    if ! "$runtime" -m pip install 'keyring>=25,<26'; then
      echo 'Keyring indisponível; será oferecida uma alternativa local.' >&2
    fi
  fi
  if $setup; then
    if [[ -t 0 ]]; then
      "$runtime" "$package" install --setup
    elif ( : </dev/tty ) 2>/dev/null; then
      "$runtime" "$package" install --setup </dev/tty
    else
      "$runtime" "$package" install
      echo 'Sem terminal interativo. Execute axurion setup depois.'
    fi
  else
    "$runtime" "$package" install
  fi
)
main "$@"
