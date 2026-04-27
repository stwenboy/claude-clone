# claude-local

A local Claude Code equivalent you can run in any terminal — useful when VPN/proxy restrictions prevent running the official VS Code extension.

It gives you the same core loop: read files, write files, make targeted edits, run shell commands, and have a persistent conversation with Claude about your codebase.

## Install

```bash
bash install.sh
```

This creates a `.venv/` virtualenv and installs `claude-local` into it.

## Usage

```bash
# Activate the venv
source .venv/bin/activate

# Set your API key
export ANTHROPIC_API_KEY=sk-ant-...

# Start in current directory
claude-local

# Start in a specific project directory
claude-local /path/to/project

# Use a corporate HTTP proxy
claude-local --proxy http://proxy.corp.com:8080

# Or via environment variable (same effect)
HTTPS_PROXY=http://proxy.corp.com:8080 claude-local
```

## Proxy support

The Anthropic SDK uses `httpx` internally, which respects standard proxy environment variables:

| Variable | Purpose |
|---|---|
| `HTTPS_PROXY` | Proxy for HTTPS traffic (Anthropic API) |
| `HTTP_PROXY` | Proxy for HTTP traffic |
| `ALL_PROXY` | Proxy for all traffic |
| `NO_PROXY` | Comma-separated list of hosts to bypass |

You can also pass `--proxy <url>` on the command line.

If your proxy uses a self-signed certificate, set:
```bash
export SSL_CERT_FILE=/path/to/ca-bundle.crt
```

## Available tools

| Tool | Description |
|---|---|
| `read_file` | Read file contents with line numbers |
| `write_file` | Create or overwrite a file |
| `edit_file` | Replace exact text in a file (like a surgical find-replace) |
| `bash` | Run any shell command |
| `list_files` | List directory contents, with optional glob pattern |

## In-session commands

| Command | Description |
|---|---|
| `/help` | Show command list |
| `/clear` | Clear conversation history |
| `/cwd` | Show working directory |
| `/model` | Show current model |
| `/exit` | Exit (also Ctrl+D) |

End a line with `\` to continue typing on the next line (multi-line input).

## Models

Defaults to `claude-sonnet-4-6`. Override with `--model`:

```bash
claude-local --model claude-opus-4-7
claude-local --model claude-haiku-4-5-20251001
```

## Requirements

- Python 3.9+
- An [Anthropic API key](https://console.anthropic.com/)
