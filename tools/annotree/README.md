# annotree

Turn a file/directory listing into a Markdown tree you can annotate item by item, then paste into Claude (desktop app or Claude Code) or send straight to `claude`.

**Platforms:** Linux, macOS, Windows (zsh, pwsh, or any other shell). **Needs:** Python 3.9+, standard library only.
It's one Python script, not a zsh script plus a PowerShell script, so both shells run the same code.

## Usage

```zsh
annotree -ec src             # list src/, open it in $EDITOR, copy the result once you close the editor
annotree --ask src           # annotate src/, then send it to `claude -p` and show the answer
annotree --chat src          # annotate src/, then start a claude session with it as the first message
annotree                     # list the current directory (one level) to stdout
annotree -d 0 src            # everything under src/, no depth limit
annotree -d 2 -D             # directories only, two levels deep
annotree --at src > todo.md  # paths as @-mentions, for Claude Code
fd -e py | annotree -c       # annotate a list piped in from another command
git diff --name-only | annotree -ec
```

```powershell
Get-ChildItem -Recurse -Name src | annotree -ec   # pipe names; formatted Get-ChildItem tables are rejected
annotree -ec .\src
```

The output of `annotree -d 2` looks like this, after filling in some notes:

```markdown
<!--
Here is a file listing of `/home/me/proj`. Under each item is a `> note:` line with my
instructions or context for that item. A note on a directory is about the directory itself;
treat it as background for the items inside, not as a separate instruction for each of them.
An empty note means I have nothing to add for that item.

The listing is 2 levels deep, so directories at the deepest level are shown without their
contents. To go deeper, re-run annotree with `-d N` for N levels, or `-d 0` for no limit.
-->

- src/
  > note: legacy code, keep the public API stable
  - main.py
    > note: entry point, don't touch
  - util.py
    > note:
- README.md
  > note: rewrite the intro
```

Fill in the notes and paste it into Claude, along with whatever you want done.

The instructions at the top are an HTML comment, so Markdown viewers hide them but Claude still
reads them when you paste. The second paragraph only appears when `--depth` actually left
directories unexpanded. Leave the comment out with `--no-header`.

### Options

| Option | Effect |
|--------|--------|
| `-d N`, `--depth N` | Descend at most N levels; `0` = no limit. Default `1` (top-level entries only) for paths, no limit for a piped list |
| `-D`, `--dirs-only` | Directories only |
| `-a`, `--all` | Include hidden files and the default excludes (`node_modules`, `__pycache__`, `venv`, `result`) |
| `-x GLOB`, `--exclude GLOB` | Skip names matching GLOB (repeatable) |
| `--no-git` | Walk the filesystem even inside a git repo |
| `--at` | Write each path as a Claude Code `@path` mention |
| `--no-header` | Leave out the instructions comment |
| `-e`, `--edit` | Open the result in `$VISUAL` / `$EDITOR` (vi or notepad if neither is set) before output |
| `-c`, `--copy` | Copy to the clipboard instead of printing |
| `-o FILE` | Write to FILE |
| `--ask` | Edit, then send the listing to `claude -p` and show the answer |
| `--chat` | Edit, then start an interactive `claude` session with the listing as the first message |

`-c`, `-o`, `--ask` and `--chat` are alternatives; pick one.

If the output can't be delivered after `-e` (the clipboard copy fails, the `-o` file can't be
written, whatever stdout is piped into has exited, or `claude` fails), annotree saves your edited
listing to a temp file and prints its path, so your notes aren't lost.
The editor always gets the terminal, even when annotree's stdin or stdout is a pipe.

### Sending it to Claude (`--ask`, `--chat`)

Both open the editor first; put your request in the notes, or anywhere in the file.
If you close the editor without changing anything, nothing is sent.
Arguments after `--` go to `claude`:

```zsh
annotree --ask src -- --model sonnet
annotree --chat -d 2 src -- --permission-mode plan
```

- `--ask` writes the listing to `claude -p` on stdin, so there's no stdin wait and no
  command-line length limit. The answer is rendered with `glow` if it's installed and stdout is a
  terminal; otherwise it's printed as plain Markdown, so `annotree --ask src > answer.md` works.
- `--chat` gives the session the terminal, so you can keep asking follow-up questions.
  On Windows it needs the native `claude.exe`. A `claude.cmd` wrapper can't pass a multi-line
  message.

| Variable | Effect |
|----------|--------|
| `ANNOTREE_CLAUDE` | The claude command, default `claude`. In WSL, `claude.exe` uses the Windows install |
| `ANNOTREE_RENDER` | Renderer for `--ask` answers, e.g. `glow -p -` or `bat -l md`. Empty prints plain Markdown |

### Piping into `claude -p` yourself

Don't run `annotree -e | claude -p`. `claude -p` gives up if no input arrives within about 3
seconds, which is long before you've finished editing. Use `--ask`, or let annotree finish first:

```zsh
claude -p "$(annotree -e)"                       # the listing becomes the prompt
annotree -e -o notes.md && claude -p < notes.md
```

Without `-e` a plain pipe works, because the listing is written immediately.

## How listings are built

- **Paths as arguments:** inside a git work tree, annotree lists the files git doesn't ignore
  (tracked and untracked), so `.gitignore` applies. Empty directories don't appear in that mode.
  Outside a repo, or with `--no-git`, it walks the filesystem without following symlinks.
  Either way, hidden names are skipped unless you pass `-a`, and the listing stops at one level
  unless you pass `-d`.
- **Piped input** (one path per line): when no paths are given and stdin is piped, annotree reads
  the list from stdin, or always does so for `-`. The list is used as given, so hidden files aren't
  filtered out and there's no depth limit by default, but `-x`, `-d` and `-D` still apply. A shared leading directory becomes the root.
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
