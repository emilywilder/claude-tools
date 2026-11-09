#!/usr/bin/env python3
"""Install the named tools, or every tool that supports this platform.

Run through `just install`, which supplies the paths and settings below.
"""

import argparse
import json
import os
import subprocess
import sys


def die(msg):
    sys.exit(f"install: {msg}")


def parse_args():
    parser = argparse.ArgumentParser(prog="install", description=__doc__)
    parser.add_argument("--just", required=True, help="path to the just executable")
    parser.add_argument("--justfile", required=True, help="path to the root justfile")
    parser.add_argument("--prefix", required=True)
    parser.add_argument("--bindir", required=True)
    parser.add_argument("--mode", required=True, help="copy or link")
    parser.add_argument("tools", nargs="*")
    return parser.parse_args()


def main():
    args = parse_args()
    tools_dir = os.path.join(os.path.dirname(os.path.abspath(args.justfile)), "tools")
    prefix = os.path.abspath(os.path.expanduser(args.prefix))
    bindir = os.path.abspath(os.path.expanduser(args.bindir))

    if args.mode not in ("copy", "link"):
        die(f"mode must be copy or link, not {args.mode!r}")

    # just only reports recipes that apply to the current OS.
    dump = json.loads(subprocess.run(
        [args.just, "--justfile", args.justfile, "--dump", "--dump-format", "json"],
        check=True, capture_output=True, text=True).stdout)
    modules = dump["modules"]
    installable = sorted(m for m, mod in modules.items() if "install" in mod["recipes"])
    folders = sorted(d for d in os.listdir(tools_dir) if os.path.isdir(os.path.join(tools_dir, d)))

    def why_not(tool):
        if tool not in folders:
            return "no such tool"
        if tool not in modules:
            return "not registered with `mod` in the root justfile"
        return "no install recipe for this platform"

    if args.tools:
        wanted = args.tools
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
    env = dict(os.environ, PREFIX=prefix, BINDIR=bindir, INSTALL_MODE=args.mode)
    failed = []
    for t in wanted:
        print(f"==> {t}", flush=True)
        if subprocess.run([args.just, "--justfile", args.justfile, f"{t}::install"], env=env).returncode:
            failed.append(t)

    if failed:
        die("failed: " + ", ".join(failed))
    path = [os.path.normcase(os.path.abspath(p)) for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    if os.path.normcase(bindir) not in path:
        print(f"note: {bindir} is not on your PATH", file=sys.stderr)
    print(f"Done: {', '.join(wanted)} -> {bindir}")


if __name__ == "__main__":
    main()
