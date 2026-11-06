# claude-tools

Personal repo of scripts/utilities/programs that help when working with Claude and Claude Code.

## Conventions

- One folder per tool under `tools/<tool-name>/` (kebab-case name).
- Every tool gets a `README.md`: one-line purpose, usage example, dependencies.
- When adding or removing a tool, update the Index table in the root `README.md`.
- Primary targets are Linux and macOS with zsh. Default languages: zsh for shell glue, Python for anything bigger.
- Other languages are welcome when the task calls for it (e.g. Rust for performance or a single static binary). Briefly note why in the tool's README.
- Windows/PowerShell is secondary and experimental. Don't make tools cross-platform by default; state the supported platforms in each tool's README.
- zsh scripts: `#!/usr/bin/env zsh` shebang, avoid GNU-only flags so they work on macOS (BSD) userland too.
- Python: `#!/usr/bin/env python3`, stdlib-only where reasonable; otherwise provide dependencies through the tool's `flake.nix`.
- Rust: standard Cargo project inside the tool's folder.
- Haskell: a Cabal project (`<tool-name>.cabal`) inside the tool's folder, built through its `flake.nix` (e.g. `haskellPackages.developPackage`, or `callCabal2nix`), with GHC, cabal-install and haskell-language-server in the devShell. Don't use Stack. Small single-file scripts can instead use a `nix-shell` shebang that runs `runghc` with `ghcWithPackages`, so they run without a build step.
- The primary Linux is NixOS. Never hardcode interpreter paths like `/bin/zsh` or `/usr/bin/python3`, because they don't exist there; always use `/usr/bin/env`.
- Both NixOS and macOS (via nix-darwin) have Nix with flakes. When a tool needs dependencies or a toolchain, use a `flake.nix` (devShell, and a package/app if useful) as the standard way to provide them.

## Testing from Windows

When working from the Windows machine, test Linux tools in WSL. The default distro is NixOS, which has zsh and python3:

```powershell
wsl -d NixOS -e zsh -c 'cd /mnt/c/Users/emily/src/claude-tools && ./tools/<name>/<script>'
```

Rust and other toolchains aren't installed globally. Get them on demand, e.g. `nix shell nixpkgs#cargo nixpkgs#rustc -c cargo build`, or `nix develop -c cabal build` for a Haskell tool that has a flake.
- Keep tools self-contained: no shared libraries unless several tools genuinely need the same code.
- Never commit secrets (API keys, tokens). Read them from environment variables.
