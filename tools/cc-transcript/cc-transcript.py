#!/usr/bin/env python3
"""Convert Claude Code session transcripts (JSONL) into readable Markdown.

Claude Code stores each session at ~/.claude/projects/<project>/<session-id>.jsonl.
The full conversation stays there even after the in-context history is compacted,
so this lets you read back everything without spending tokens on it.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# --------------------------------------------------------------------------- #
# Locating transcripts
# --------------------------------------------------------------------------- #


def claude_dir() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else Path.home() / ".claude"


def project_dir_for(cwd: Path) -> Path:
    # Claude Code names project folders after the cwd with every
    # non-alphanumeric character replaced by '-'.
    name = re.sub(r"[^A-Za-z0-9]", "-", str(cwd))
    return claude_dir() / "projects" / name


def session_files(proj: Path) -> list[Path]:
    if not proj.is_dir():
        return []
    return sorted(proj.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)


def resolve_input(arg: str | None, proj: Path) -> Path:
    if arg:
        p = Path(arg).expanduser()
        if p.is_file():
            return p
        # Treat as a session id (or unique prefix) in this project or any project.
        candidates = list(proj.glob(f"{arg}*.jsonl")) or list(
            (claude_dir() / "projects").glob(f"*/{arg}*.jsonl")
        )
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            sys.exit(f"cc-transcript: '{arg}' matches several sessions:\n"
                     + "\n".join(f"  {c}" for c in candidates))
        sys.exit(f"cc-transcript: no file or session matching '{arg}'")
    files = session_files(proj)
    if not files:
        sys.exit(f"cc-transcript: no transcripts found in {proj}")
    return files[0]


# --------------------------------------------------------------------------- #
# Reading
# --------------------------------------------------------------------------- #


def load(path: Path) -> list[dict]:
    entries = []
    with path.open(encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                print(f"cc-transcript: skipping bad JSON on line {n}", file=sys.stderr)
    return entries


def session_title(entries: list[dict]) -> str | None:
    title = None
    for e in entries:
        if e.get("type") == "ai-title" and e.get("aiTitle"):
            title = e["aiTitle"]  # keep the latest
    return title


def first_prompt(entries: list[dict]) -> str | None:
    for e in entries:
        if e.get("type") == "user" and not e.get("isMeta"):
            c = e.get("message", {}).get("content")
            if isinstance(c, str) and c.strip():
                return clean_user_text(c)
    return None


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #

REMINDER_RE = re.compile(r"<system-reminder>.*?</system-reminder>\s*", re.S)


def clean_user_text(text: str) -> str:
    text = REMINDER_RE.sub("", text)
    # Slash commands are logged as XML-ish tags; render them as the user typed them.
    m = re.search(r"<command-name>(.*?)</command-name>", text, re.S)
    if m:
        args = re.search(r"<command-args>(.*?)</command-args>", text, re.S)
        cmd = m.group(1).strip()
        return f"`{cmd}{(' ' + args.group(1).strip()) if args and args.group(1).strip() else ''}`"
    m = re.search(r"<local-command-stdout>(.*?)</local-command-stdout>", text, re.S)
    if m:
        return fence(m.group(1).strip())
    return escape_tags(text.strip())


def fence(text: str, lang: str = "") -> str:
    longest = max((len(r) for r in re.findall(r"`+", text)), default=0)
    ticks = "`" * max(3, longest + 1)
    return f"{ticks}{lang}\n{text.rstrip()}\n{ticks}"


def truncate(text: str, max_lines: int) -> str:
    if max_lines <= 0:
        return text
    lines = text.splitlines()
    if len(lines) <= max_lines:
        return text
    return "\n".join(lines[:max_lines]) + f"\n… ({len(lines) - max_lines} more lines)"


def local_time(ts: str | None) -> str:
    if not ts:
        return ""
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone()
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return ts


def one_line(s: str, width: int = 100) -> str:
    s = " ".join(str(s).split())
    return s if len(s) <= width else s[: width - 1] + "…"


def html_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


CODE_RE = re.compile(r"(^(`{3,}|~{3,}).*?^\2[ \t]*$|`+[^`\n]*?`+)", re.S | re.M)
TAG_RE = re.compile(r"<(?=/?[A-Za-z!])")


def escape_tags(text: str) -> str:
    """Stop Markdown viewers from swallowing <tag>-like text, leaving code untouched."""
    out, pos = [], 0
    for m in CODE_RE.finditer(text):
        out.append(TAG_RE.sub("&lt;", text[pos:m.start()]))
        out.append(m.group(0))
        pos = m.end()
    out.append(TAG_RE.sub("&lt;", text[pos:]))
    return "".join(out)


LANG_BY_EXT = {
    ".py": "python", ".sh": "sh", ".zsh": "zsh", ".rs": "rust", ".hs": "haskell",
    ".ps1": "powershell", ".js": "javascript", ".ts": "typescript", ".json": "json",
    ".md": "markdown", ".nix": "nix", ".toml": "toml", ".yaml": "yaml", ".yml": "yaml",
    ".html": "html", ".css": "css", ".cabal": "cabal",
}


def lang_for(path: str) -> str:
    return LANG_BY_EXT.get(Path(path).suffix.lower(), "")


# --------------------------------------------------------------------------- #
# Tool calls
# --------------------------------------------------------------------------- #


def tool_summary(name: str, inp: dict) -> str:
    for key in ("description", "file_path", "pattern", "url", "query", "prompt", "command"):
        if isinstance(inp.get(key), str) and inp[key].strip():
            return one_line(inp[key])
    return ""


def render_tool_input(name: str, inp: dict, max_lines: int) -> str:
    if name in ("Bash", "PowerShell") and "command" in inp:
        return fence(truncate(inp["command"], max_lines), "sh" if name == "Bash" else "powershell")
    if name == "Edit" and "old_string" in inp:
        diff = "\n".join(
            [f"- {l}" for l in inp["old_string"].splitlines()]
            + [f"+ {l}" for l in inp["new_string"].splitlines()]
        )
        return f"`{inp.get('file_path', '')}`\n\n" + fence(truncate(diff, max_lines), "diff")
    if name == "Write" and "content" in inp:
        path = inp.get("file_path", "")
        return f"`{path}`\n\n" + fence(truncate(inp["content"], max_lines), lang_for(path))
    if name == "Read":
        return f"`{inp.get('file_path', '')}`"
    return fence(truncate(json.dumps(inp, indent=2, ensure_ascii=False), max_lines), "json")


def result_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for b in content:
            if b.get("type") == "text":
                parts.append(b.get("text", ""))
            elif b.get("type") == "image":
                parts.append("[image]")
            else:
                parts.append(f"[{b.get('type', 'unknown')} block]")
        return "\n".join(parts)
    return "" if content is None else str(content)


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


class Renderer:
    def __init__(self, args, entries: list[dict]):
        self.args = args
        self.entries = entries
        self.out: list[str] = []
        self.current_role: str | None = None
        self.results: dict[str, dict] = {}
        for e in entries:
            c = e.get("message", {}).get("content") if e.get("type") == "user" else None
            if isinstance(c, list):
                for b in c:
                    if b.get("type") == "tool_result":
                        self.results[b.get("tool_use_id")] = b

    def emit(self, s: str = "") -> None:
        self.out.append(s)

    def heading(self, role: str, ts: str | None) -> None:
        if role == self.current_role:
            return
        self.current_role = role
        when = local_time(ts)
        self.emit(f"## {role}" + (f" · {when}" if when and self.args.timestamps else ""))
        self.emit()

    def header(self, path: Path) -> None:
        title = session_title(self.entries) or one_line(first_prompt(self.entries) or path.stem, 80)
        meta = next((e for e in self.entries if e.get("type") in ("user", "assistant")), {})
        last = next((e for e in reversed(self.entries) if e.get("timestamp")), {})
        self.emit(f"# {title}")
        self.emit()
        rows = [
            ("Session", f"`{meta.get('sessionId', path.stem)}`"),
            ("Directory", f"`{meta.get('cwd', '')}`" if meta.get("cwd") else ""),
            ("Branch", f"`{meta.get('gitBranch')}`" if meta.get("gitBranch") else ""),
            ("Started", local_time(meta.get("timestamp"))),
            ("Last activity", local_time(last.get("timestamp"))),
        ]
        for k, v in rows:
            if v:
                self.emit(f"- **{k}:** {v}")
        self.emit()
        self.emit("---")
        self.emit()

    def render(self, path: Path) -> str:
        self.header(path)
        seen: set[str] = set()
        for e in self.entries:
            uid = e.get("uuid")
            if uid:
                if uid in seen:
                    continue
                seen.add(uid)
            if e.get("isSidechain") and not self.args.sidechains:
                continue
            t = e.get("type")
            if t == "user":
                self.user(e)
            elif t == "assistant":
                self.assistant(e)
            elif t == "system" and e.get("subtype") == "compact_boundary":
                self.current_role = None
                self.emit("---")
                self.emit()
                self.emit(f"> **Context compacted** · {local_time(e.get('timestamp'))}")
                self.emit()
        return "\n".join(self.out).rstrip() + "\n"

    def user(self, e: dict) -> None:
        msg = e.get("message", {})
        content = msg.get("content")
        if e.get("isCompactSummary"):
            self.current_role = None
            self.emit("<details><summary>Compaction summary</summary>")
            self.emit()
            self.emit(escape_tags(result_text(content).strip()))
            self.emit()
            self.emit("</details>")
            self.emit()
            return
        if e.get("isMeta"):
            return
        parts: list[str] = []
        if isinstance(content, str):
            parts.append(clean_user_text(content))
        elif isinstance(content, list):
            for b in content:
                bt = b.get("type")
                if bt == "text":
                    parts.append(clean_user_text(b.get("text", "")))
                elif bt == "image":
                    parts.append("*[image]*")
                # tool_result blocks are rendered alongside their tool_use
        parts = [p for p in parts if p]
        if not parts:
            return
        self.heading("User", e.get("timestamp"))
        for p in parts:
            self.emit(p)
            self.emit()

    def assistant(self, e: dict) -> None:
        content = e.get("message", {}).get("content")
        if isinstance(content, str):
            content = [{"type": "text", "text": content}]
        for b in content or []:
            bt = b.get("type")
            if bt == "text" and b.get("text", "").strip():
                self.heading("Claude", e.get("timestamp"))
                self.emit(escape_tags(b["text"].strip()))
                self.emit()
            elif bt == "thinking" and self.args.thinking and b.get("thinking", "").strip():
                self.heading("Claude", e.get("timestamp"))
                self.emit("<details><summary><i>Thinking</i></summary>")
                self.emit()
                self.emit(escape_tags(b["thinking"].strip()))
                self.emit()
                self.emit("</details>")
                self.emit()
            elif bt == "tool_use" and self.args.tools != "none":
                self.heading("Claude", e.get("timestamp"))
                self.tool_use(b)

    def tool_use(self, b: dict) -> None:
        name = b.get("name", "tool")
        inp = b.get("input") or {}
        res = self.results.get(b.get("id"))
        failed = bool(res and res.get("is_error"))
        summary = tool_summary(name, inp)
        label = f"<b>{html_escape(name)}</b>" + (f" — {html_escape(summary)}" if summary else "")
        if failed:
            label += " ⚠️"
        if self.args.tools == "brief":
            self.emit(f"<details><summary>{label}</summary>")
            self.emit()
        else:
            self.emit(f"**{name}**" + (f" — {summary}" if summary else "") + (" ⚠️" if failed else ""))
            self.emit()
        self.emit(render_tool_input(name, inp, self.args.max_lines))
        self.emit()
        if res is not None:
            text = result_text(res.get("content")).replace("\r\n", "\n").strip()
            if text:
                self.emit("Error:" if failed else "Result:")
                self.emit()
                self.emit(fence(truncate(text, self.args.max_lines)))
                self.emit()
        if self.args.tools == "brief":
            self.emit("</details>")
            self.emit()


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def list_sessions(proj: Path) -> None:
    files = session_files(proj)
    if not files:
        sys.exit(f"cc-transcript: no transcripts found in {proj}")
    for f in files:
        entries = load(f)
        title = session_title(entries) or one_line(first_prompt(entries) or "", 60)
        mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
        print(f"{mtime}  {f.stem}  {title}")


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="cc-transcript",
        description="Convert a Claude Code session transcript (JSONL) to Markdown.",
    )
    ap.add_argument("session", nargs="?",
                    help="path to a .jsonl file, or a session id/prefix "
                         "(default: most recent session for the project dir)")
    ap.add_argument("-o", "--output", help="write to this file instead of stdout")
    ap.add_argument("-C", "--project", default=".",
                    help="project directory whose sessions to use (default: current dir)")
    ap.add_argument("-l", "--list", action="store_true", help="list sessions for the project and exit")
    ap.add_argument("--tools", choices=["brief", "full", "none"], default="brief",
                    help="brief: collapsible <details> (default); full: expanded; none: omit tool calls")
    ap.add_argument("--max-lines", type=int, default=40,
                    help="truncate tool inputs/outputs to N lines (0 = no limit, default 40)")
    ap.add_argument("--thinking", action="store_true", help="include thinking blocks when present")
    ap.add_argument("--sidechains", action="store_true", help="include subagent (sidechain) messages")
    ap.add_argument("--no-timestamps", dest="timestamps", action="store_false",
                    help="omit timestamps from message headings")
    args = ap.parse_args()

    proj = project_dir_for(Path(args.project).expanduser().resolve())
    if args.list:
        list_sessions(proj)
        return

    path = resolve_input(args.session, proj)
    md = Renderer(args, load(path)).render(path)

    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdout.write(md)


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        sys.exit(0)
