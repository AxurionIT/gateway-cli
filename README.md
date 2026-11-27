# Axurion Gateway CLI · v1.2.0-beta.4

A cross-platform client for the Axurion AI Gateway, built around CLIProxyAPI and virtual models such as `astra-coding`. It does not host models, modify the gateway, or include credentials. The server remains responsible for quota-aware routing, fallbacks, and session affinity.

## Quick installation

Requires Python 3.11+ and OpenCode v2 for the default experience. Codex CLI 0.134.0+ is optional. Install only on authorized machines and networks.

### Install via GitHub Releases (v1.2.0-beta.4)

Install this experimental beta from its versioned release after publication. Do not run a script you have not reviewed or whose source you do not trust. The bootstrap downloads the `.pyz` and SHA-256 checksum from the same versioned release, verifies integrity, and only then installs it. The checksum is not an independent digital signature.

**macOS / Linux (quick command):**

```sh
curl -fsSL --proto '=https' --proto-redir '=https' https://github.com/AxurionIT/gateway-cli/releases/download/v1.2.0-beta.4/install.sh | bash
```

Alternative for reviewing before execution:

```sh
curl -fsSL --proto '=https' --proto-redir '=https' https://github.com/AxurionIT/gateway-cli/releases/download/v1.2.0-beta.4/install.sh -o install.sh
# Review the file before running it.
bash install.sh
```

**Windows (PowerShell):**

```powershell
$installer = Join-Path $env:TEMP 'axurion-install.ps1'
Invoke-WebRequest -Uri 'https://github.com/AxurionIT/gateway-cli/releases/download/v1.2.0-beta.4/install.ps1' -OutFile $installer
# Review the file before running it.
& $installer
```

Respect the PowerShell execution policy. If necessary, use the `.pyz` package directly after verifying its SHA-256 checksum; do not change managed security policies. Python 3.11+ is still required on all platforms: the `.pyz` is portable, not a self-contained native binary.

Use `bash install.sh --no-setup` or `./install.ps1 -NoSetup` to install or update only, without prompting for a key or modifying the profile. `--offline` / `-Offline` avoids installing keyring from PyPI, but the bootstrap still downloads the package if it is not available locally. For a network-free installation, use the complete ZIP and offline mode. The installer does not modify PATH automatically; see the instructions below.

### Publishing a release

The release workflow tests on Linux, macOS, and Windows before publishing the tagged build and its SHA-256 checksum. Beta versions are marked as prereleases and must be installed using their versioned URLs, not `releases/latest`.

### macOS and Linux

Extract the ZIP, open a terminal in the `gateway-cli` folder, and run:

```sh
bash install.sh
```

The installer creates its own virtual environment, attempts to install `keyring` from PyPI to use the system vault, and then prompts for the Base URL and API Key. It does not use sudo. If necessary, add `~/.local/bin` to your shell's PATH:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

To make this persistent, add that line to `~/.zshrc` (zsh) or your shell's configuration file. Alternatively, run `~/.local/bin/axurion` directly.

### Windows

Open PowerShell in the extracted folder:

```powershell
.\install.ps1
```

If the execution policy blocks scripts, use the direct method below instead of changing managed policies. The installer does not modify PATH automatically. Add `%LOCALAPPDATA%\Axurion\bin` to the user's PATH when authorized, or run the launcher directly:

```powershell
& "$env:LOCALAPPDATA\Axurion\bin\axurion.cmd" status
```

### Direct / offline installation

Download `gateway-cli.pyz`, which contains the CLI code with no mandatory external dependencies:

```sh
python3 gateway-cli.pyz install --setup
```

On Windows, use `py -3 gateway-cli.pyz install --setup`. If no vault is available, explicitly choose `env` or `file`. You can also use `bash install.sh --offline` or `./install.ps1 -Offline` in the complete distribution. Offline mode does not install dependencies.

Another option for developers: run `pipx install '.[secure]'` in the source folder, followed by `axurion setup` (pipx maintains the Python environment).

## Configuration

The default is `https://ai.axurion.com.br/v1`. To use a local gateway, provide its loopback URL during setup, for example `http://127.0.0.1:8317/v1`. HTTPS is required outside loopback. Installation does not create domains or change DNS, VPNs, certificates, or firewall settings. The default remote URL has not been verified in this environment.

```sh
axurion setup
axurion status
axurion models
```

Setup makes no network calls and consumes no tokens. `status` and `models` query the catalog without inference; they do not prove that all models or tiers are available. `test` asks for confirmation before a single minimal inference (the provider's output limit is not guaranteed):

```sh
axurion test --effort medium
axurion test --effort high --protocol chat
```

Each test uses a unique session identifier. It does not test xhigh automatically. Check the dashboard to confirm the provider actually selected.

### Codex / Orca

```sh
codex --profile axurion
axurion codex
axurion codex --effort high
axurion codex --effort xhigh
axurion codex --model astra-coding --effort medium
axurion codex --effort high -- exec "Analyze this project"
```

Running `codex` without a profile continues to use the original configuration. The CLI writes a separate `~/.codex/axurion.config.toml` profile (or under `$CODEX_HOME`), with `wire_api = "responses"` and external-command authentication. The main configuration is not overwritten; conflicts are rejected, and older managed profiles are backed up when changed. The profile disables web search by default without changing global Codex settings. Use `axurion profile` to rebuild it. If the installation's Python is removed, reinstall the CLI and run `axurion profile` to refresh the helper path.

In Orca or another frontend that actually runs Codex CLI, configure the `codex` command with the `--profile axurion` argument when the frontend permits it. Alternatively, open the integrated terminal and run `axurion codex`. The profile does not require exporting a global variable if the key is in the vault or a file. Graphical frontends may override the model or provider or use different processes or environments; integration must be verified in the actual client. The CLI does not automatically modify Orca, Monocode, Cursor, OpenBot, or Hermes.

Session affinity depends on the gateway recognizing a native client session identifier. The CLI sends a unique ID in its own tests, but does not inject a static ID into every Codex session; the gateway plugin must recognize native identifiers or receive a per-session header. Do not use the API Key as a session identifier.

## Commands

| Command | Action | Inference? |
|---|---|---|
| `axurion setup` | Configure URL, credential, model, and profile | No |
| `axurion login` | Change the local key | No |
| `axurion logout` | Remove the locally stored key; does not revoke it on the server | No |
| `axurion models` | List models from `/v1/models` | No |
| `axurion status` | Authenticated HTTP diagnostic | No |
| `axurion doctor` | Local Python, Codex, and credential diagnostic | No |
| `axurion config` | Show settings without the key | No |
| `axurion profile` | Recreate the managed profile | No |
| `axurion usage` | Usage from this CLI's tests; dashboard link | No |
| `axurion usage --server` | Aggregate API key counters via the v8/v0 management API | No |
| `axurion dashboard` | Open the Axurion dashboard (requires authorized access) | No |
| `axurion test` | Short inference with confirmation; `--yes` explicitly confirms | Yes |
| `axurion codex` | Start Codex with the Axurion profile | Depending on use |
| `axurion update path/to/gateway-cli.pyz` | Update from a trusted local package | No |

`models`, `status`, and `usage` support `--json`. `setup` supports `--url`, `--model`, `--effort`, and `--storage`. Remote usage requires a separate management key, entered without echo and not persisted. Never share this key with agents; use local or private administration. The command aggregates only numeric success/failure counts, without exposing IDs that may contain secrets. The counters endpoint may not represent OAuth, all models, tokens, or quotas. The dashboard is the source for gateway metrics. `update` verifies downloaded release checksums, but does not validate an independent cryptographic signature. For pipx installations, update through pipx instead of using `update`.

## Credentials and security

- `keyring`: uses a known system vault implementation, if available. The installer does not silently fall back to plaintext.
- `env`: uses `AXURION_API_KEY`; the application does not write the key. Configure the secret using an authorized mechanism on your system. The environment must be inherited by Codex.
- `file`: an explicit, **unencrypted** option. Uses 0600 permissions on Unix; on Windows, it depends on the user folder's ACLs. Do not use on shared devices.
- If `AXURION_API_KEY` is set, it takes precedence over local storage. Do not inadvertently reuse the variable for another server.
- The key is requested without echo, is not written to TOML or passed as an argument to Codex, and does not appear in diagnostics. The helper returns the key to the Codex process when requested; a process with access to your account may still access it.
- TLS is validated; HTTP redirects are rejected by CLI calls. The CLI does not modify network controls, ignore certificates, or configure policy evasion.
- No key backup is created. The previous installer's profile may have left a plaintext key in `~/.codex/axurion-credentials/gateway.key`; after validating the migration and revoking old keys, review and remove that file manually.
- Use separate, least-privilege keys per device or agent. Revoke the key on the gateway when necessary. Logout is local only.

## Development

```sh
python -m unittest discover -s tests -v
python scripts/build.py
python dist/gateway-cli.pyz --version
```

CI is configured for Linux, macOS, and Windows (Python 3.11 and 3.13). HTTP tests use a fake loopback server. Vault dependencies and real graphical clients require testing on each platform. No real inference requests were made during development. This version does not include automatic Codex installation or a Homebrew/Winget package. The publishing workflow is included but must be run in the actual repository.

References: [Codex advanced configuration](https://learn.chatgpt.com/docs/config-file/config-advanced), [CLIProxyAPI management v8](https://github.com/router-for-me/CLIProxyAPI/blob/main/docs/management-api-v8.md), [keyring](https://keyring.readthedocs.io/en/stable/).

### Multi-harness development preview

This is an experimental prerelease, not the stable v1.2.0 release. OpenCode v2 can be configured with `axurion sync opencode`, which reads `/models` without inference and manages only the `axurion` provider. Start it with `axurion` or `axurion opencode --model astra-coding --effort high`. The API key is passed in the child process environment and is not written to the OpenCode configuration. Running OpenCode directly requires `AXURION_API_KEY` in its environment. Existing unmanaged Axurion entries and JSONC configuration cause a safe refusal instead of replacement. Remove the managed provider with `axurion uninstall opencode`.

OpenCode v2.3.2 provider loading, launch and reasoning payloads were tested with a simulated local gateway, not the production gateway. The provider targets the OpenCode v2 configuration format, not v1. Gateway support for reasoning routing and session affinity has not been verified. Pi can launch catalogue models with thinking disabled; when limits are unavailable Pi applies its own defaults, which must be verified against the gateway; reasoning selection is rejected until its mapping is verified. Claude Code requires an explicit Claude model and compatible Anthropic gateway; protocol compatibility is unverified. Existing Codex behavior is retained. Do not use this preview as evidence of production compatibility.

### Multi-harness development status

See [compatibility and external validation](docs/multi-harness.md), and the [changelog](CHANGELOG.md). These integrations are under development: a mocked
client launch is not evidence of gateway protocol or routing compatibility.

OpenCode makes a separate low-effort request to generate a session title. In a simulated test, rejecting this auxiliary request did not prevent the main high-effort answer, but actual gateway behavior and title handling are unverified. The main request retains the selected effort.

### Atualização da CLI

`axurion update` consulta as releases GitHub e instala a versão mais recente do canal atual; `axurion update --check` apenas verifica. Use `--beta` para a pré-release mais recente, `--version v1.2.3` para uma tag específica ou `--rollback` para restaurar o pacote anterior. Uma versão beta permanece no canal beta por padrão; a atualização normal nunca faz downgrade. `axurion update /caminho/gateway-cli.pyz` continua aceitando um pacote local confiável.

A verificação automática ocorre em segundo plano, no máximo uma vez a cada 24 horas, com resultado em cache; ela não instala nada e falhas de rede são silenciosas. Para desativá-la, defina `AXURION_NO_UPDATE_CHECK=1` ou adicione `"auto_check": false` ao arquivo `update.json` em `AXURION_HOME` (padrão: `~/.config/axurion`, ou `%LOCALAPPDATA%/Axurion` no Windows). O mesmo arquivo pode conter `"channel": "stable"` ou `"channel": "beta"`. Uma atualização explícita para outro canal altera essa preferência.

Pacotes remotos são verificados com SHA-256 antes da instalação; o checksum vem da mesma release e não constitui assinatura independente. O pacote anterior fica em `gateway-cli.pyz.bak` no diretório de configuração. Credenciais e integrações não são modificadas. Em sistemas que não permitem substituir um arquivo em uso, a atualização falha sem remover a instalação existente.
