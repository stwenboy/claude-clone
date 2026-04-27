#!/usr/bin/env python3
"""A local Claude Code equivalent — AI coding assistant in your terminal."""

import json
import os
import subprocess
import sys
import argparse
from pathlib import Path
from typing import Optional

try:
    import readline
    READLINE_AVAILABLE = True
except ImportError:
    READLINE_AVAILABLE = False

try:
    import anthropic
except ImportError:
    print("Error: anthropic package not installed. Run: pip install anthropic rich")
    sys.exit(1)

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
except ImportError:
    print("Error: rich package not installed. Run: pip install anthropic rich")
    sys.exit(1)

console = Console()

TOOLS = [
    {
        "name": "read_file",
        "description": (
            "Read the contents of a file. Returns content with line numbers (format: 'N\\tcontent'). "
            "Read files before editing them."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative path to the file"},
                "offset": {"type": "integer", "description": "Line number to start reading from (1-indexed)"},
                "limit": {"type": "integer", "description": "Maximum number of lines to read"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": "Write content to a file, creating it (and any parent directories) if needed. Overwrites existing files.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative path to the file"},
                "content": {"type": "string", "description": "Full content to write"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "edit_file",
        "description": (
            "Replace an exact string in a file. old_string must match exactly (including whitespace/indentation). "
            "If old_string appears more than once, provide more surrounding context to make it unique, "
            "or set replace_all=true to replace every occurrence."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute or relative path to the file"},
                "old_string": {"type": "string", "description": "Exact text to replace"},
                "new_string": {"type": "string", "description": "Text to replace it with"},
                "replace_all": {"type": "boolean", "description": "Replace all occurrences (default: false)"},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    {
        "name": "bash",
        "description": (
            "Execute a shell command and return stdout + stderr. "
            "Use for running tests, builds, git commands, grep, find, etc."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to execute"},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30)"},
            },
            "required": ["command"],
        },
    },
    {
        "name": "list_files",
        "description": "List files and directories under a path. Supports glob patterns.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path (default: current directory)"},
                "pattern": {"type": "string", "description": "Glob pattern, e.g. '**/*.py', '*.ts'"},
            },
        },
    },
]

SYSTEM_PROMPT = """\
You are Claude Code, an AI coding assistant running locally in the user's terminal. \
You help with software engineering tasks: writing and fixing code, refactoring, explaining code, \
running shell commands, managing files, and more.

You have tools for reading files, writing files, making targeted edits, running shell commands, \
and listing directories. Use them proactively to explore the codebase and make changes.

Guidelines:
- Always read a file before editing it so you have the current content
- Prefer editing existing files over creating new ones
- Run tests after making changes to verify correctness
- Keep changes focused — don't refactor beyond what's asked
- Use bash for codebase exploration (find, grep, git log, etc.)
- Never commit unless explicitly asked

Current working directory: {cwd}\
"""


# ── Tool implementations ────────────────────────────────────────────────────

def _read_file(path: str, offset: Optional[int] = None, limit: Optional[int] = None) -> str:
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return f"Error: file not found: {path}"
        if p.is_dir():
            return f"Error: {path} is a directory"
        lines = p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
        start = max(0, (offset - 1) if offset else 0)
        end = min(len(lines), (start + limit) if limit else len(lines))
        numbered = [f"{i}\t{line}" for i, line in enumerate(lines[start:end], start + 1)]
        return "".join(numbered) or "(empty file)"
    except Exception as e:
        return f"Error: {e}"


def _write_file(path: str, content: str) -> str:
    try:
        p = Path(path).expanduser()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"


def _edit_file(path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return f"Error: file not found: {path}"
        content = p.read_text(encoding="utf-8", errors="replace")
        if old_string not in content:
            return (
                f"Error: old_string not found in {path}. "
                "Verify the exact text including whitespace and indentation."
            )
        count = content.count(old_string)
        if not replace_all and count > 1:
            return (
                f"Error: old_string appears {count} times in {path}. "
                "Provide more surrounding context to make it unique, or set replace_all=true."
            )
        new_content = content.replace(old_string, new_string) if replace_all else content.replace(old_string, new_string, 1)
        p.write_text(new_content, encoding="utf-8")
        replaced = count if replace_all else 1
        return f"Replaced {replaced} occurrence(s) in {path}"
    except Exception as e:
        return f"Error: {e}"


def _bash(command: str, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        out = ""
        if result.stdout:
            out += result.stdout
        if result.stderr:
            out += result.stderr
        if result.returncode != 0:
            out += f"\n[exit {result.returncode}]"
        return out.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"


def _list_files(path: str = ".", pattern: Optional[str] = None) -> str:
    try:
        p = Path(path).expanduser()
        if not p.exists():
            return f"Error: path not found: {path}"
        if not p.is_dir():
            return f"Error: {path} is not a directory"
        entries = sorted(p.glob(pattern) if pattern else p.iterdir())
        if not entries:
            return "(empty)"
        lines = []
        for e in entries:
            if e.is_dir():
                lines.append(f"{e.name}/")
            else:
                size = e.stat().st_size
                size_str = (
                    f"{size}B" if size < 1024
                    else f"{size // 1024}KB" if size < 1024 ** 2
                    else f"{size // 1024 ** 2}MB"
                )
                lines.append(f"{e.name}  ({size_str})")
        return "\n".join(lines)
    except Exception as e:
        return f"Error: {e}"


def execute_tool(name: str, inp: dict) -> str:
    if name == "read_file":
        return _read_file(inp["path"], inp.get("offset"), inp.get("limit"))
    if name == "write_file":
        return _write_file(inp["path"], inp["content"])
    if name == "edit_file":
        return _edit_file(inp["path"], inp["old_string"], inp["new_string"], inp.get("replace_all", False))
    if name == "bash":
        return _bash(inp["command"], inp.get("timeout", 30))
    if name == "list_files":
        return _list_files(inp.get("path", "."), inp.get("pattern"))
    return f"Error: unknown tool '{name}'"


def _tool_label(name: str, inp: dict) -> str:
    if name == "bash":
        return f"$ {inp.get('command', '')}"
    if name == "read_file":
        suffix = f":{inp['offset']}" if inp.get("offset") else ""
        return f"read {inp['path']}{suffix}"
    if name == "write_file":
        return f"write {inp['path']}"
    if name == "edit_file":
        return f"edit {inp['path']}"
    if name == "list_files":
        return f"ls {inp.get('path', '.')}"
    return f"{name}({json.dumps(inp)[:60]})"


# ── Agent loop ──────────────────────────────────────────────────────────────

def run_agent(client: "anthropic.Anthropic", messages: list, cwd: str, model: str) -> None:
    system = SYSTEM_PROMPT.format(cwd=cwd)

    while True:
        response = client.messages.create(
            model=model,
            max_tokens=8096,
            system=system,
            tools=TOOLS,
            messages=messages,
        )

        text_parts = []
        tool_uses = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_uses.append(block)

        if text_parts:
            console.print(Markdown("\n".join(text_parts)))

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn" or not tool_uses:
            break

        tool_results = []
        for tu in tool_uses:
            label = _tool_label(tu.name, tu.input)
            console.print(f"[dim cyan]  ⚙  {label}[/dim cyan]")

            result = execute_tool(tu.name, tu.input)

            preview_lines = result.split("\n")
            if len(preview_lines) > 4:
                console.print(f"[dim]     → ({len(preview_lines)} lines)[/dim]")
            else:
                for line in preview_lines[:4]:
                    if line.strip():
                        console.print(f"[dim]     → {line[:100]}[/dim]")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})


# ── Multi-line input ────────────────────────────────────────────────────────

def read_input() -> str:
    """
    Read user input. Lines ending with \\ continue to the next line.
    An empty first line with no continuation returns empty string.
    """
    lines = []
    first = True
    while True:
        prompt = "[bold green]>[/bold green] " if first else "[bold green]…[/bold green] "
        try:
            line = console.input(prompt)
        except EOFError:
            raise
        first = False
        if line.endswith("\\"):
            lines.append(line[:-1])
        else:
            lines.append(line)
            break
    return "\n".join(lines).strip()


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="claude-local — AI coding assistant (Claude Code equivalent)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Environment variables:
  ANTHROPIC_API_KEY    Your Anthropic API key (required)
  HTTPS_PROXY          HTTPS proxy, e.g. http://proxy.corp.com:8080
  HTTP_PROXY           HTTP proxy
  ALL_PROXY            Proxy for all protocols

Examples:
  claude-local
  claude-local /path/to/project
  HTTPS_PROXY=http://proxy:8080 claude-local
  claude-local --proxy http://proxy:8080
  claude-local --model claude-opus-4-7
""",
    )
    parser.add_argument("directory", nargs="?", default=".", help="Working directory (default: .)")
    parser.add_argument("--model", default="claude-sonnet-4-6", help="Claude model ID")
    parser.add_argument("--proxy", help="Proxy URL (sets HTTPS_PROXY and HTTP_PROXY)")
    args = parser.parse_args()

    if args.proxy:
        os.environ["HTTPS_PROXY"] = args.proxy
        os.environ["HTTP_PROXY"] = args.proxy

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        console.print("[red]Error:[/red] ANTHROPIC_API_KEY is not set.")
        console.print("  export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    cwd = str(Path(args.directory).expanduser().resolve())
    if not Path(cwd).is_dir():
        console.print(f"[red]Error:[/red] Directory not found: {cwd}")
        sys.exit(1)

    os.chdir(cwd)

    # httpx (used by the Anthropic SDK) automatically picks up HTTPS_PROXY / HTTP_PROXY
    client = anthropic.Anthropic(api_key=api_key)

    proxy_info = f"  proxy: {os.environ.get('HTTPS_PROXY', 'none')}\n" if os.environ.get("HTTPS_PROXY") else ""
    console.print(
        Panel.fit(
            f"[bold blue]claude-local[/bold blue]  [dim]({args.model})[/dim]\n"
            f"  dir: {cwd}\n"
            f"{proxy_info}"
            f"  /help  /clear  /exit  |  end a line with \\ to continue on the next line",
            border_style="blue",
        )
    )

    messages: list = []

    if READLINE_AVAILABLE:
        readline.set_history_length(500)
        history_file = Path.home() / ".claude_local_history"
        try:
            readline.read_history_file(str(history_file))
        except FileNotFoundError:
            pass
    else:
        history_file = None

    while True:
        console.print()
        try:
            user_input = read_input()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye![/dim]")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            cmd = user_input[1:].split()[0].lower()
            if cmd in ("exit", "quit", "q"):
                console.print("[dim]Goodbye![/dim]")
                break
            elif cmd == "clear":
                messages.clear()
                console.clear()
                console.print("[dim]Conversation cleared.[/dim]")
            elif cmd == "help":
                console.print(
                    Panel(
                        "/clear   Clear conversation history\n"
                        "/exit    Exit (also: Ctrl+D)\n"
                        "/cwd     Show working directory\n"
                        "/model   Show current model\n"
                        "/reset   Alias for /clear\n"
                        "\n"
                        "End a line with \\ to continue typing on the next line.",
                        title="Commands",
                        border_style="dim",
                    )
                )
            elif cmd == "cwd":
                console.print(f"[dim]{cwd}[/dim]")
            elif cmd == "model":
                console.print(f"[dim]{args.model}[/dim]")
            elif cmd == "reset":
                messages.clear()
                console.print("[dim]Conversation cleared.[/dim]")
            else:
                console.print(f"[yellow]Unknown command:[/yellow] {user_input}  (type /help)")
            continue

        messages.append({"role": "user", "content": user_input})
        console.print()

        try:
            run_agent(client, messages, cwd, args.model)
        except KeyboardInterrupt:
            console.print("\n[dim](interrupted)[/dim]")
            # Remove the unanswered user message so history stays consistent
            if messages and messages[-1]["role"] == "user":
                messages.pop()
        except anthropic.APIConnectionError as e:
            console.print(f"[red]Connection error:[/red] {e}")
            proxy = os.environ.get("HTTPS_PROXY")
            if proxy:
                console.print(f"  Using proxy: {proxy}")
            else:
                console.print("  Tip: set HTTPS_PROXY or use --proxy if behind a corporate proxy.")
            if messages and messages[-1]["role"] == "user":
                messages.pop()
        except anthropic.AuthenticationError:
            console.print("[red]Authentication error:[/red] invalid ANTHROPIC_API_KEY")
            break
        except anthropic.RateLimitError:
            console.print("[yellow]Rate limit hit — wait a moment and try again.[/yellow]")
            if messages and messages[-1]["role"] == "user":
                messages.pop()
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            if messages and messages[-1]["role"] == "user":
                messages.pop()

    if READLINE_AVAILABLE and history_file:
        try:
            readline.write_history_file(str(history_file))
        except Exception:
            pass


if __name__ == "__main__":
    main()
