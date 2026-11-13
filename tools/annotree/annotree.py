#!/usr/bin/env python3
"""annotree: turn a file/directory listing into an annotatable Markdown tree for Claude.

Each item gets a `> note:` line underneath it. Fill in the notes (instructions,
context, ...), then paste the result into Claude or Claude Code.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap

# Skipped unless --all. Hidden names (leading dot) are skipped too.
DEFAULT_EXCLUDES = {"node_modules", "__pycache__", "venv", "result"}

AT_WARN_THRESHOLD = 50
SIZE_WARN_THRESHOLD = 1000


class Node:
    __slots__ = ("name", "is_dir", "path", "children")

    def __init__(self, name: str, is_dir: bool, path: str):
        self.name = name
        self.is_dir = is_dir
        self.path = path  # '/'-separated path used for @-mentions
        self.children: dict[str, Node] = {}

    def child(self, name: str, is_dir: bool) -> "Node":
        node = self.children.get(name)
        if node is None:
            node = self.children[name] = Node(name, is_dir, join(self.path, name))
        elif is_dir:
            node.is_dir = True
        return node

    def count(self) -> tuple[int, int]:
        """(dirs, files) below this node."""
        d = f = 0
        for c in self.children.values():
            if c.is_dir:
                d += 1
            else:
                f += 1
            cd, cf = c.count()
            d += cd
            f += cf
        return d, f


def join(a: str, b: str) -> str:
    if a in ("", "."):
        return b
    return a.rstrip("/") + "/" + b


def norm(p: str) -> str:
    """Normalise a user-supplied path: '/' separators, no './' prefix, no trailing '/'."""
    if os.sep != "/":
        p = p.replace(os.sep, "/")
    while p.startswith("./"):
        p = p[2:]
    if len(p) > 1:
        p = p.rstrip("/")
    return p or "."


def mention_path(p: str) -> str:
    """Path relative to the cwd if it's inside it, else as given."""
    if os.path.isabs(p):
        rel = os.path.relpath(p)
        if not rel.startswith(".."):
            return norm(rel)
    return norm(p)


def warn(msg: str) -> None:
    print(f"annotree: {msg}", file=sys.stderr)


# --------------------------------------------------------------------------- building


class Builder:
    def __init__(self, opts: argparse.Namespace):
        self.opts = opts
        self.truncated = False  # some directory was left unexpanded because of --depth

    def skip(self, name: str, explicit: bool = False) -> bool:
        if any(fnmatch.fnmatch(name, pat) for pat in self.opts.exclude):
            return True
        if explicit or self.opts.all:
            return False
        return name.startswith(".") or name in DEFAULT_EXCLUDES

    def deeper(self, depth: int) -> bool:
        return self.opts.depth is None or depth < self.opts.depth

    def fill_dir(self, node: Node, fspath: str) -> None:
        """Populate `node` with the contents of directory `fspath`."""
        files = None if self.opts.no_git else git_files(fspath)
        if files is not None:
            for rel in files:
                self.insert(node, rel.split("/"), fspath)
        else:
            self.walk(node, fspath, 1)

    def walk(self, node: Node, fspath: str, depth: int) -> None:
        try:
            entries = list(os.scandir(fspath))
        except OSError as e:
            warn(f"can't read {fspath}: {e.strerror}")
            return
        for e in entries:
            if self.skip(e.name):
                continue
            try:
                is_dir = e.is_dir(follow_symlinks=False)
            except OSError:
                is_dir = False
            if self.opts.dirs_only and not is_dir:
                continue
            c = node.child(e.name, is_dir)
            if is_dir:
                if self.deeper(depth):
                    self.walk(c, e.path, depth + 1)
                else:
                    self.truncated = True

    def insert(self, node: Node, parts: list[str], fsroot: str | None,
               explicit: bool = False, dir_hint: bool = False) -> None:
        """Insert a relative path (split into parts) below `node`.

        fsroot: directory the parts are relative to, used to check what's on disk
        (None means the parts are a full path as given).
        """
        last = len(parts) - 1
        for i, part in enumerate(parts):
            if self.skip(part, explicit):
                return
            if i < last:
                node = node.child(part, True)
                if not self.deeper(i + 1):
                    self.truncated = True
                    return  # truncated at --depth: keep the dir, drop its contents
                continue
            if fsroot is None:
                is_dir = dir_hint
            else:
                full = os.path.join(fsroot, *parts)
                if not os.path.lexists(full):
                    return  # tracked by git but deleted on disk
                is_dir = os.path.isdir(full)
            if self.opts.dirs_only and not is_dir:
                return
            node.child(part, is_dir)

    def from_args(self, paths: list[str]) -> tuple[Node, str | None]:
        if len(paths) == 1 and os.path.isdir(paths[0]):
            p = paths[0]
            root = Node("", True, mention_path(p) if os.path.isabs(p) else norm(p))
            self.fill_dir(root, p)
            return root, os.path.abspath(p)

        root = Node("", True, "")
        for p in paths:
            if not os.path.lexists(p):
                warn(f"no such file or directory: {p}")
                continue
            is_dir = os.path.isdir(p)
            label = norm(p)
            c = root.children.setdefault(label, Node(label, is_dir, mention_path(p)))
            if is_dir and self.deeper(0):
                self.fill_dir(c, p)
        return root, os.getcwd()

    def from_lines(self, lines: list[str]) -> tuple[Node, str | None]:
        items: list[tuple[list[str], bool]] = []
        for line in lines:
            raw = line.strip()
            if not raw:
                continue
            hint = raw.endswith(("/", os.sep))
            p = norm(raw)
            if p == ".":
                continue
            parts = p.split("/")
            if parts[0] == "":  # absolute unix path
                parts[0] = "/"
            items.append((parts, hint or os.path.isdir(p)))
        if not items:
            return Node("", True, ""), None

        # Factor out the longest common directory prefix as the root.
        prefix = items[0][0][:-1]
        for parts, _ in items[1:]:
            n = 0
            while n < len(prefix) and n < len(parts) - 1 and parts[n] == prefix[n]:
                n += 1
            prefix = prefix[:n]
        root_path = "/".join(prefix).replace("//", "/") if prefix else ""
        root = Node("", True, mention_path(root_path) if root_path else "")
        for parts, is_dir in items:
            rel = parts[len(prefix):]
            if self.opts.dirs_only and not is_dir:
                rel = rel[:-1]  # keep its parent dirs
                if not rel:
                    continue
                is_dir = True
            self.insert(root, rel, None, explicit=True, dir_hint=is_dir)
        return root, root_path or None


def git_files(d: str) -> list[str] | None:
    """Files under `d` that git doesn't ignore, or None if `d` isn't in a git work tree."""
    if not shutil.which("git"):
        return None
    try:
        r = subprocess.run(
            ["git", "-C", d, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
            capture_output=True,
        )
    except OSError:
        return None
    if r.returncode != 0:
        return None
    out = r.stdout.decode("utf-8", "surrogateescape")
    return sorted({p for p in out.split("\0") if p})


# --------------------------------------------------------------------------- output


def render(root: Node, root_label: str | None, opts: argparse.Namespace,
           truncated: bool) -> str:
    out: list[str] = []
    if not opts.no_header:
        where = f" of `{root_label}`" if root_label else ""
        paras = [
            f"Here is a file listing{where}. Under each item is a `> note:` line with "
            "my instructions or context for that item. A note on a directory is about the "
            "directory itself; treat it as background for the items inside, not as a "
            "separate instruction for each of them. An empty note means I have nothing "
            "to add for that item."
        ]
        if truncated:
            n = opts.depth
            paras.append(
                f"The listing is {n} level{'s' if n != 1 else ''} deep, so directories at "
                "the deepest level are shown without their contents. To go deeper, re-run "
                "annotree with `-d N` for N levels, or `-d 0` for no limit."
            )
        out.append("<!--")
        for i, p in enumerate(paras):
            if i:
                out.append("")
            # Keep `code spans` on one line: protect their spaces while wrapping.
            p = re.sub(r"`[^`]*`", lambda m: m.group().replace(" ", "\0"), p)
            p = p.replace("--", "- -")  # "--" can't appear inside an HTML comment
            out.extend(line.replace("\0", " ") for line in
                       textwrap.wrap(p, 90, break_on_hyphens=False))
        out.append("-->")
        out.append("")

    def walk(node: Node, indent: int) -> None:
        pad = "  " * indent
        kids = sorted(node.children.values(), key=lambda n: (not n.is_dir, n.name.lower(), n.name))
        for c in kids:
            label = "@" + c.path if opts.at else c.name
            if c.is_dir and not label.endswith("/"):
                label += "/"
            out.append(f"{pad}- {label}")
            out.append(f"{pad}  > note: ")
            walk(c, indent + 1)

    walk(root, 0)
    return "\n".join(out) + "\n"


def split_command(spec: str) -> list[str]:
    return shlex.split(spec, posix=os.name != "nt")


def run_on_terminal(cmd: list[str]) -> int:
    """Run an interactive program. If our stdin or stdout is a pipe (input list piped
    in, result piped on to another command), give the program the terminal instead."""
    def tty(name, mode):
        try:
            return open(name, mode)
        except OSError:
            return None
    stdin = None if sys.stdin.isatty() else tty("CONIN$" if os.name == "nt" else "/dev/tty", "r")
    stdout = None if sys.stdout.isatty() else tty("CONOUT$" if os.name == "nt" else "/dev/tty", "w")
    try:
        return subprocess.run(cmd, stdin=stdin, stdout=stdout).returncode
    finally:
        for f in (stdin, stdout):
            if f:
                f.close()


def open_in_editor(text: str) -> str:
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or (
        "notepad" if os.name == "nt" else "vi")
    cmd = split_command(editor)
    exe = shutil.which(cmd[0])  # resolves e.g. code.cmd on Windows
    if exe is None:
        sys.exit(f"annotree: editor not found: {cmd[0]} (set VISUAL or EDITOR)")
    fd, path = tempfile.mkstemp(prefix="annotree-", suffix=".md")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        rc = run_on_terminal([exe, *cmd[1:], path])
        if rc != 0:
            sys.exit(f"annotree: editor exited with status {rc}; nothing copied")
        with open(path, encoding="utf-8") as f:
            return f.read()
    finally:
        os.unlink(path)


def is_wsl() -> bool:
    if os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        with open("/proc/version") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def copy_to_clipboard(text: str) -> str | None:
    """Copy `text` to the clipboard. Returns an error message, or None on success."""
    def run(cmd: list[str], data: bytes, env: dict | None = None) -> str | None:
        try:
            subprocess.run(cmd, input=data, env=env, check=True)
        except (OSError, subprocess.CalledProcessError) as e:
            return f"{cmd[0]} failed: {e}"
        return None

    if os.name == "nt" or (sys.platform.startswith("linux") and is_wsl()):
        clip = shutil.which("clip.exe") or shutil.which("clip")
        if clip:
            data = text.replace("\r\n", "\n").replace("\n", "\r\n")
            return run([clip], data.encode("utf-16-le"))
    if sys.platform == "darwin":
        return run(["pbcopy"], text.encode(), dict(os.environ, LC_CTYPE="UTF-8"))
    candidates = []
    if os.environ.get("WAYLAND_DISPLAY"):
        candidates.append(["wl-copy"])
    candidates += [["xclip", "-selection", "clipboard"], ["xsel", "--clipboard", "--input"]]
    for cmd in candidates:
        if shutil.which(cmd[0]):
            return run(cmd, text.encode())
    return "no clipboard tool found (need wl-copy, xclip, xsel, pbcopy or clip.exe)"


def claude_command() -> list[str] | str:
    """The claude command ($ANNOTREE_CLAUDE, default `claude`), or an error message."""
    cmd = split_command(os.environ.get("ANNOTREE_CLAUDE") or "claude")
    exe = shutil.which(cmd[0]) if cmd else None
    if exe is None:
        return f"{cmd[0] if cmd else 'claude'} not found (set ANNOTREE_CLAUDE)"
    return [exe, *cmd[1:]]


def renderer() -> list[str] | None:
    """Command to render Markdown answers with: $ANNOTREE_RENDER (empty = none),
    else `glow -` if it's installed and stdout is a terminal."""
    spec = os.environ.get("ANNOTREE_RENDER")
    if spec is None:
        glow = shutil.which("glow")
        return [glow, "-"] if glow and sys.stdout.isatty() else None
    cmd = split_command(spec)
    if not cmd:
        return None
    exe = shutil.which(cmd[0])
    if exe is None:
        warn(f"renderer not found: {cmd[0]}; showing the raw answer")
        return None
    return [exe, *cmd[1:]]


def ask_claude(claude: list[str], text: str) -> str | None:
    """Send `text` to `claude -p` on stdin and show the answer. Returns an error or None."""
    render = renderer()
    warn("waiting for claude...")
    try:
        # The listing goes in on stdin right away, so claude doesn't wait for input,
        # and a long listing doesn't run into command-line length limits.
        r = subprocess.run([*claude, "-p"], input=text.encode("utf-8"),
                           stdout=subprocess.PIPE if render else None)
    except OSError as e:
        return f"cannot run {claude[0]}: {e}"
    if r.returncode:
        return f"claude exited with status {r.returncode}"
    if render:
        try:
            subprocess.run(render, input=r.stdout, check=True)
        except (OSError, subprocess.CalledProcessError) as e:
            warn(f"{os.path.basename(render[0])} failed ({e}); showing the raw answer")
            sys.stdout.buffer.write(r.stdout)
            sys.stdout.flush()
    return None


def chat_with_claude(claude: list[str], text: str) -> str | None:
    """Start an interactive claude session with `text` as the first message."""
    if os.name == "nt" and claude[0].lower().endswith((".cmd", ".bat")):
        return (f"--chat can't pass a multi-line message through {os.path.basename(claude[0])}; "
                "install the native claude.exe or use --ask")
    try:
        # `--` so a listing starting with "- " (--no-header) isn't read as an option.
        rc = run_on_terminal([*claude, "--", text])
    except OSError as e:  # e.g. the listing is too long for a command line
        return f"cannot run {claude[0]}: {e}"
    return f"claude exited with status {rc}" if rc else None


def read_stdin_lines() -> list[str]:
    data = sys.stdin.buffer.read().decode("utf-8", "replace").lstrip("﻿")
    lines = data.splitlines()
    head = "\n".join(lines[:8])
    if "Directory:" in head and "LastWriteTime" in head:
        sys.exit("annotree: that looks like formatted Get-ChildItem output; "
                 "pipe names instead, e.g. `Get-ChildItem -Recurse -Name | annotree`")
    return lines


# --------------------------------------------------------------------------- main


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(
        prog="annotree",
        description="Turn a file/directory listing into a Markdown tree you can annotate "
                    "and paste into Claude.",
        epilog="With no paths and piped input, reads one path per line from stdin "
               "(e.g. `fd | annotree`, `git ls-files | annotree`, "
               "`Get-ChildItem -Recurse -Name | annotree`). "
               "With --ask or --chat, arguments after `--` are passed to claude "
               "(e.g. `annotree --ask src -- --model sonnet`). "
               "ANNOTREE_CLAUDE sets the claude command (default: claude); "
               "ANNOTREE_RENDER sets the --ask renderer (default: `glow -` if installed "
               "and stdout is a terminal; empty for none).",
    )
    ap.add_argument("paths", nargs="*",
                    help="files/directories to list (default: stdin if piped, else .); "
                         "'-' reads stdin")
    ap.add_argument("-d", "--depth", type=int, metavar="N",
                    help="descend at most N levels; 0 = no limit (default: 1 for paths, "
                         "no limit for a piped list)")
    ap.add_argument("-a", "--all", action="store_true",
                    help="include hidden files and default excludes ("
                         + ", ".join(sorted(DEFAULT_EXCLUDES)) + ")")
    ap.add_argument("-x", "--exclude", action="append", default=[], metavar="GLOB",
                    help="skip names matching GLOB (repeatable)")
    ap.add_argument("-D", "--dirs-only", action="store_true", help="list directories only")
    ap.add_argument("--no-git", action="store_true",
                    help="walk the filesystem even inside a git repo (don't apply .gitignore)")
    ap.add_argument("--at", action="store_true",
                    help="write paths as Claude Code @-mentions, so Claude reads the files")
    ap.add_argument("--no-header", action="store_true",
                    help="leave out the instructions comment at the top")
    ap.add_argument("-e", "--edit", action="store_true",
                    help="open the result in $VISUAL/$EDITOR before output")
    dest = ap.add_mutually_exclusive_group()
    dest.add_argument("-c", "--copy", action="store_true",
                      help="copy to the clipboard instead of printing")
    dest.add_argument("-o", "--output", metavar="FILE", help="write to FILE instead of stdout")
    dest.add_argument("--ask", action="store_true",
                      help="edit, then send the listing to `claude -p` and show the answer")
    dest.add_argument("--chat", action="store_true",
                      help="edit, then start an interactive claude session with the listing "
                           "as the first message")

    # With --ask/--chat, everything after `--` is for claude.
    argv, claude_args = sys.argv[1:], []
    if "--" in argv:
        i = argv.index("--")
        if "--ask" in argv[:i] or "--chat" in argv[:i]:
            argv, claude_args = argv[:i], argv[i + 1:]
    opts = ap.parse_args(argv)
    if opts.ask or opts.chat:
        opts.edit = True
        claude = claude_command()
        if isinstance(claude, str):  # check before the editing, not after
            sys.exit(f"annotree: {claude}")
        claude += claude_args

    if opts.depth is not None and opts.depth < 0:
        ap.error("--depth can't be negative")

    use_stdin = opts.paths == ["-"] or (not opts.paths and not sys.stdin.isatty())
    lines = read_stdin_lines() if use_stdin else []
    from_stdin = any(line.strip() for line in lines)
    if opts.paths == ["-"] and not from_stdin:
        sys.exit("annotree: no paths on stdin")

    # A piped list is already the selection you want, so it isn't cut short by default.
    if opts.depth is None:
        opts.depth = 0 if from_stdin else 1
    if opts.depth == 0:
        opts.depth = None

    b = Builder(opts)
    if from_stdin:
        root, label = b.from_lines(lines)
    else:
        root, label = b.from_args([p for p in opts.paths if p != "-"] or ["."])

    dirs, files = root.count()
    if dirs + files == 0:
        sys.exit("annotree: nothing to list")
    if dirs + files > SIZE_WARN_THRESHOLD:
        warn(f"{dirs + files} items; consider --depth, --dirs-only or --exclude")
    if opts.at and files > AT_WARN_THRESHOLD:
        warn(f"--at with {files} files: Claude Code will load every one of them into context")

    text = render(root, label, opts, b.truncated)
    if opts.edit:
        original = text
        text = open_in_editor(text)
        if (opts.ask or opts.chat) and text == original:
            sys.exit("annotree: no notes added, so nothing was sent to claude")

    def fail(err: str):
        if opts.edit:  # don't lose the notes that were just typed
            fd, saved = tempfile.mkstemp(prefix="annotree-", suffix=".md")
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            warn(f"your edited listing is saved in {saved}")
        sys.exit(f"annotree: {err}")

    if opts.ask or opts.chat:
        try:
            err = (ask_claude if opts.ask else chat_with_claude)(claude, text)
        except KeyboardInterrupt:
            err = "interrupted"
        if err:
            fail(err)
    elif opts.copy:
        err = copy_to_clipboard(text)
        if err:
            fail(err)
        warn(f"copied {dirs} dirs, {files} files to the clipboard")
    elif opts.output:
        try:
            with open(opts.output, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        except OSError as e:
            fail(f"cannot write {opts.output}: {e}")
    else:
        try:
            sys.stdout.write(text)
            sys.stdout.flush()
        except OSError as e:  # e.g. the reader (`claude -p`) gave up and exited
            # Point stdout at devnull so the flush at exit doesn't raise again.
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
            fail("output pipe closed before the listing was written"
                 if isinstance(e, BrokenPipeError) else f"cannot write output: {e}")


if __name__ == "__main__":
    main()
