# cc-transcript

Convert a Claude Code session transcript into readable Markdown, without using any tokens.

Claude Code writes every session to `~/.claude/projects/<project>/<session-id>.jsonl`.
That file keeps the **whole** conversation even after the in-context history gets compacted,
so you can review earlier output with this tool after compaction.

**Platforms:** Linux, macOS, Windows. **Needs:** Python 3.9+, standard library only.

## Usage

```zsh
cc-transcript                      # most recent session for the current directory → stdout
cc-transcript -o session.md        # write to a file
cc-transcript --list               # list this project's sessions (newest first, with titles)
cc-transcript bfea5a94             # pick a session by id or id prefix (searches all projects if needed)
cc-transcript path/to/file.jsonl   # convert a specific transcript
cc-transcript -C ~/src/other-repo  # use another project's sessions
```

Pipe it into a pager or renderer, e.g. `cc-transcript | glow -p` or `cc-transcript | bat -l md`.

### Options

| Option | Effect |
|--------|--------|
| `--tools brief` | Tool calls as collapsible `<details>` blocks (default) |
| `--tools full` | Tool calls fully expanded |
| `--tools none` | Only the conversation text |
| `--max-lines N` | Truncate tool inputs and outputs to N lines (default 40, `0` = no limit) |
| `--thinking` | Include thinking blocks (they're often stored redacted, so may be empty) |
| `--sidechains` | Include subagent messages |
| `--no-timestamps` | Leave timestamps out of message headings |

## What the output contains

- A header with the session title, id, directory, branch and time span.
- `## User` / `## Claude` sections. Consecutive assistant steps are merged into one section.
- Each tool call next to its result. Failed calls are marked ⚠️, and Edit calls are shown as diffs.
- Compaction points, marked **Context compacted**, with the compaction summary in a collapsible block.
- Slash commands shown as the command you typed. `<system-reminder>` blocks and internal records are left out.
- Tag-like text such as `<use_case>` is escaped so Markdown viewers don't hide it.

## Install

From the repo root:

```zsh
just install cc-transcript              # copy to ~/.local/bin
just mode=link install cc-transcript    # or symlink, so repo edits apply immediately
```

On Windows this also writes a `cc-transcript.cmd` launcher that runs the script with `python`.
In link mode the launcher points at the repo copy.

## Notes

- The transcript format is internal to Claude Code and undocumented, so a future version could change it. Unknown record types are ignored rather than causing errors.
- Entries are rendered in file order. If you rewound a conversation, abandoned branches may still appear.
- `CLAUDE_CONFIG_DIR` is respected if you've moved `~/.claude`.
