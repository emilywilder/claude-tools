# claude-tools. Run `just` to list recipes.

import 'just/install.just'

# One line per tool. A tool supports a platform if its justfile has an
# `install` recipe for it (plain, or tagged [unix]/[linux]/[macos]/[windows]).
mod annotree 'tools/annotree'
mod cc-transcript 'tools/cc-transcript'

[private]
default:
    @just --justfile '{{justfile()}}' --list --list-submodules

# Install the named tools, or every tool that supports this platform
install *tools:
    @python3 {{quote(source_directory() / "just" / "install.py")}} \
        --just {{quote(just_executable())}} --justfile {{quote(justfile())}} \
        --prefix {{quote(prefix)}} --bindir {{quote(bindir)}} --mode {{quote(mode)}} \
        {{tools}}
