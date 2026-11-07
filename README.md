# claude-tools

A personal collection of scripts, utilities, and small programs for working with Claude / Claude Code.

## Layout

Each tool lives in its own folder under `tools/`, with a short `README.md` explaining what it does and how to run it.

```
justfile             # root: `just install`, plus one `mod` line per tool
just/install.just    # shared install settings (prefix, bindir, mode)
tools/
  <tool-name>/
    README.md
    justfile         # the tool's recipes, at least `install`
    <source files>
```

## Installing

Installation uses [just](https://github.com/casey/just) (1.58+). Get it with
`nix shell nixpkgs#just`, `brew install just`, or `scoop install just` / `winget install Casey.Just`.

```zsh
just                                   # list recipes
just install                           # every tool that supports this OS, into ~/.local/bin
just install cc-transcript             # only the named tools
just prefix=/opt/ct install            # executables go to /opt/ct/bin
just bindir=~/bin install              # override only the bin dir
just mode=link install                 # link back into the repo, so edits apply without reinstalling
just cc-transcript::install            # run one tool's recipe directly
```

`prefix`, `bindir` and `mode` can also come from the `PREFIX`, `BINDIR` and `INSTALL_MODE`
environment variables. The prefix defaults to `~/.local`.

**Platforms:** the installer runs on Linux, macOS and Windows. Each tool decides which of those
it supports. On Windows, recipes run in PowerShell 7 (`pwsh`), and the install recipe needs
`python3` on `PATH`.

### Making a tool installable

1. Add `tools/<name>/justfile`. It imports the shared settings and defines `install`:

   ```just
   import '../../just/install.just'

   [unix]
   install:
       nix shell nixpkgs#cargo nixpkgs#rustc -c cargo build --release
       install -m 755 target/release/<name> {{quote(bindir)}}/
   ```

2. Register it in the root `justfile`: `mod <name> 'tools/<name>'`.

The recipe gets these variables:

| Variable | Meaning |
|----------|---------|
| `prefix` | Installation prefix |
| `bindir` | Where executables go. Usually `prefix/bin`; create it in the recipe |
| `mode` | `copy` or `link`. Tools with nothing to link, such as compiled binaries, can ignore it |

Notes for writing recipes:
- Use `source_directory()` for paths inside the tool's folder. `justfile_directory()` points at the repo root.
- Tag recipes with `[unix]`, `[linux]`, `[macos]` or `[windows]` for the platforms the tool supports. A tool with no `install` recipe for the current OS is skipped by `just install`.
- On Windows, every recipe line runs in a new `pwsh` process. Use a `[script("pwsh", ...)]` recipe when lines need to share variables.
- Unstable just features are fine; add `set unstable` to the justfile that uses them.

## Index

| Tool | What it does |
|------|--------------|
| [cc-transcript](tools/cc-transcript/) | Convert Claude Code session transcripts (JSONL) to readable Markdown, including after compaction |
