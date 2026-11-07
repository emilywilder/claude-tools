# claude-tools. Run `just` to list recipes.

import 'just/install.just'

set positional-arguments

# One line per tool. A tool supports a platform if its justfile has an
# `install` recipe for it (plain, or tagged [unix]/[linux]/[macos]/[windows]).
mod cc-transcript 'tools/cc-transcript'

[private]
default:
    @just --justfile '{{justfile()}}' --list --list-submodules

# Install the named tools, or every tool that supports this platform
[script("python3")]
install *tools:
    import json, os, subprocess, sys

    JUST = r'''{{just_executable()}}'''
    JUSTFILE = r'''{{justfile()}}'''
    TOOLS_DIR = os.path.join(r'''{{justfile_directory()}}''', "tools")
    prefix = os.path.abspath(os.path.expanduser(r'''{{prefix}}'''))
    bindir = os.path.abspath(os.path.expanduser(r'''{{bindir}}'''))
    mode = r'''{{mode}}'''

    def die(msg):
        sys.exit(f"install: {msg}")

    if mode not in ("copy", "link"):
        die(f"mode must be copy or link, not {mode!r}")

    # just only reports recipes that apply to the current OS.
    dump = json.loads(subprocess.run(
        [JUST, "--justfile", JUSTFILE, "--dump", "--dump-format", "json"],
        check=True, capture_output=True, text=True).stdout)
    modules = dump["modules"]
    installable = sorted(m for m, mod in modules.items() if "install" in mod["recipes"])
    folders = sorted(d for d in os.listdir(TOOLS_DIR) if os.path.isdir(os.path.join(TOOLS_DIR, d)))

    def why_not(tool):
        if tool not in folders:
            return "no such tool"
        if tool not in modules:
            return "not registered with `mod` in the root justfile"
        return "no install recipe for this platform"

    if sys.argv[1:]:
        wanted = sys.argv[1:]
        problems = [f"{t}: {why_not(t)}" for t in wanted if t not in installable]
        if problems:
            die("\n  ".join(["cannot install:", *problems]))
    else:
        wanted = installable
        for t in folders:
            if t not in installable:
                print(f"skip  {t} ({why_not(t)})", file=sys.stderr)
        if not wanted:
            die("nothing to install")

    os.makedirs(bindir, exist_ok=True)
    env = dict(os.environ, PREFIX=prefix, BINDIR=bindir, INSTALL_MODE=mode)
    failed = []
    for t in wanted:
        print(f"==> {t}", flush=True)
        if subprocess.run([JUST, "--justfile", JUSTFILE, f"{t}::install"], env=env).returncode:
            failed.append(t)

    if failed:
        die("failed: " + ", ".join(failed))
    path = [os.path.normcase(os.path.abspath(p)) for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    if os.path.normcase(bindir) not in path:
        print(f"note: {bindir} is not on your PATH", file=sys.stderr)
    print(f"Done: {', '.join(wanted)} -> {bindir}")
