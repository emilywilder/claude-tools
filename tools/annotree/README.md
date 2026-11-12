# annotree

Turn a file/directory listing into a Markdown tree you can annotate item by item, then paste into Claude (desktop app or Claude Code).

**Platforms:** Linux, macOS, Windows (zsh, pwsh, or any other shell). **Needs:** Python 3.9+, standard library only.
It's one Python script, not a zsh script plus a PowerShell script, so both shells run the same code.

## Usage

```zsh
annotree -ec src             # list src/, open it in $EDITOR, copy the result once you close the editor
annotree                     # list the current directory to stdout
annotree -d 2 -D             # directories only, two levels deep
annotree --at src > todo.md  # paths as @-mentions, for Claude Code
fd -e py | annotree -c       # annotate a list piped in from another command
git diff --name-only | annotree -ec
```

```powershell
Get-ChildItem -Recurse -Name src | annotree -ec   # pipe names; formatted Get-ChildItem tables are rejected
annotree -ec .\src
```

The output looks like this:

```markdown
Here is a file listing of `/home/me/proj`. Under each item is a `> note:` line with my
instructions or context for that item. A note on a directory is about the directory itself;
treat it as background for the items inside, not as a separate instruction for each of them.
An empty note means I have nothing to add for that item.

- src/
  > note: legacy code, keep the public API stable
  - main.py
    > note: entry point, don't touch
  - util.py
    > note:
- README.md
  > note: rewrite the intro
```

Fill in the notes and paste it into Claude, along with whatever you want done. You can delete
the header sentence, or leave it out with `--no-header`.

### Options

| Option | Effect |
|--------|--------|
| `-d N`, `--depth N` | Descend at most N levels (`1` = top-level entries only) |
| `-D`, `--dirs-only` | Directories only |
| `-a`, `--all` | Include hidden files and the default excludes (`node_modules`, `__pycache__`, `venv`, `result`) |
| `-x GLOB`, `--exclude GLOB` | Skip names matching GLOB (repeatable) |
| `--no-git` | Walk the filesystem even inside a git repo |
| `--at` | Write each path as a Claude Code `@path` mention |
| `--no-header` | Leave out the explanatory sentence |
| `-e`, `--edit` | Open the result in `$VISUAL` / `$EDITOR` (vi or notepad if neither is set) before output |
| `-c`, `--copy` | Copy to the clipboard instead of printing |
| `-o FILE` | Write to FILE |

## How listings are built

- **Paths as arguments:** inside a git work tree, annotree lists the files git doesn't ignore
  (tracked and untracked), so `.gitignore` applies. Empty directories don't appear in that mode.
  Outside a repo, or with `--no-git`, it walks the filesystem without following symlinks.
  Either way, hidden names are skipped unless you pass `-a`.
- **Piped input** (one path per line): when no paths are given and stdin is piped, annotree reads
  the list from stdin, or always does so for `-`. The list is used as given, so hidden files aren't
  filtered out, but `-x`, `-d` and `-D` still apply. A shared leading directory becomes the root.
  An entry counts as a directory if it ends in `/`, other entries sit under it, or it's a
  directory relative to the current directory.
- Directories sort before files, case-insensitively.

## @-mentions (`--at`)

In Claude Code, `@path` attaches the file's contents (a directory gives its listing).
Use `--at` when you want Claude to read the files next to your notes. Paths are relative to
the current directory, so run annotree from where you run `claude`. Every @-mentioned file goes
into context, so keep these lists short (annotree warns above 50 files). The desktop app doesn't
resolve @-mentions, so leave out `--at` there. Paths containing spaces may not resolve.

## Clipboard

`-c` uses `clip.exe` on Windows and WSL, `pbcopy` on macOS, and `wl-copy`, `xclip` or `xsel` on Linux.

## Install

```zsh
just install annotree              # copy to ~/.local/bin
just mode=link install annotree    # or symlink, so repo edits apply immediately
```

On Windows this also writes an `annotree.cmd` launcher that runs the script with `python`.
