---
name: make-pages-interactive
description: Turn a directory of static HTML pages into a live commenting surface. Injects a feedback library, starts a tiny server, and routes user comments into a JSONL inbox that the agent watches and responds to by editing the pages. Works in Claude Code and Codex. Trigger phrases — "make this page interactive", "make these pages interactive", "let me comment on this page", "add feedback to these pages", "check feedback", "process pending feedback".
---

# Make Pages Interactive

Turns any folder of HTML files into a place the user can leave inline comments on (text selections, element selections, page-level notes). Comments POST to a local JSONL inbox; you (the agent) wait for that inbox, edit the HTML in response, append to `feedback/history.json`, and the page auto-reloads with a walkthrough of what changed.

**Paths:** `<skill>` below means the directory containing this SKILL.md (e.g. `~/.claude/skills/make-pages-interactive` or `~/.codex/skills/make-pages-interactive`). `<dir>` is the folder of HTML pages.

**Pick your mode once, by what your harness offers:**
- **Watch mode** — you can run a command in the background *and* get notified when a file changes (Claude Code: Bash `run_in_background` + the `Monitor` tool).
- **Wait mode** — anything else (Codex, etc.): your shell commands must return, and nothing wakes you between turns. You block on `scripts/wait_for_feedback.py` instead.

## When to invoke

User says any of:
- "make this page interactive" / "make these pages interactive" → **Setup flow**
- "add feedback to this page" / "let me comment on this page" → **Setup flow**
- "set up feedback on <dir>" → **Setup flow**
- "check feedback" / "process pending feedback" → **Pending check**
- "stop the feedback server" / "kill the server" / "shut it down" → **Stop flow**
- "remove the feedback layer" / "make pages static again" → **Removal flow**
- "update the make-pages-interactive skill" → **Update flow**

## Setup flow

1. **Identify the target directory.** Usually the user's current working directory or a folder they named. If ambiguous, ask.
2. **Inject the feedback tags** into every `*.html` in that directory:
   ```
   python <skill>/scripts/inject.py <dir>
   ```
   Add `--recursive` if the pages live in subfolders. Idempotent — safe to re-run. Also creates `<dir>/feedback/inbox.jsonl` and `<dir>/feedback/history.json` if missing.
3. **Start (or reuse) the server.**
   - **Wait mode** (and fine in any harness):
     ```
     python <skill>/scripts/start_server.py <dir>
     ```
     It reuses a server already serving `<dir>` on ports 5050–5059, otherwise starts one detached on the first free port, waits until it answers, and prints the URLs. The server survives the command returning and exits by itself after 10 min with no browser open. Log: `<dir>/feedback/server.log`. If it fails because the sandbox blocks binding a local port, re-run it with escalated permissions / approval.
   - **Watch mode** (Claude Code): first `curl -s --max-time 2 http://localhost:5050/info`. JSON with `artifact_dir` = `<dir>` → reuse it. JSON for a different dir → try 5051, 5052, …. No response → free. Then run, with `run_in_background: true`:
     ```
     python <skill>/lib/server.py <dir> --port <chosen>
     ```
     This one also shuts down when the Claude Code session ends.
4. **Tell the user the URL(s)**, e.g. `http://localhost:5050/index.html` (use their actual filenames; list the top-level pages if there are several). Pages only work through the server — not opened as files.
5. **Process anything already pending** (see **Pending check**), then **wait for comments**:
   - **Watch mode:** start a `Monitor` on `<dir>/feedback/inbox.jsonl`. Do NOT poll — let the notification arrive, then go to **Responding to feedback**.
   - **Wait mode:** loop:
     ```
     python <skill>/scripts/wait_for_feedback.py <dir> --timeout 300
     ```
     Give the command a timeout longer than `--timeout` (e.g. 330 s). Exit 0 → it printed `{"pending": [...]}`; handle them (**Responding to feedback**), then run it again. Exit 2 → nothing arrived; run it again. If the command is cut off by your tool timeout, lower `--timeout` and keep looping. After ~30 min with no comments, stop and tell the user: "say *check feedback* when you've left more comments." Keep your messages between iterations to one short line.

## Responding to feedback

Each comment has a stable `id` (like `c-1730000000000-ab12`), a `type` (`selection`, `elements`, or `page`), the user's `comment` text, and anchor info (selector, `text_snippet`, `outer_html`) pointing at what they commented on. Use `page_url` to find the file.

1. **(Optional, recommended for anything > a few seconds)** post a status line so the user sees what you're doing:
   ```
   curl -s -X POST http://localhost:<port>/status -H 'Content-Type: application/json' \
     -d '{"comment_id": "<comment id>", "message": "Rewriting the intro (~20s)"}'
   ```
   `message: null` or `""` clears it. Entries auto-expire after 10 min.
2. **Edit the HTML** to address each comment. Wrap each modified region with `<span data-cf-change="ch-<short-slug>">…</span>` (or add `data-cf-change` to an existing wrapping element) so the post-reload walkthrough can find it. One anchor per change.
3. **Append** a batch object to the END of the array in `<dir>/feedback/history.json` (newest = last; the page walks from the end). Write it atomically (write a temp file, then rename) so the polling page never reads half a file:
   ```json
   {
     "batch_id": "b-<timestamp-or-slug>",
     "timestamp": "<ISO 8601>",
     "comments": [ /* echo back the inbox comments you addressed */ ],
     "changes": [
       {
         "id": "ch-<slug>",
         "in_response_to": ["<comment id>"],
         "anchor": "ch-<slug>",
         "title": "short, concrete",
         "description": "longer prose (hidden in UI, just for the record)"
       }
     ]
   }
   ```
   - `in_response_to` holds the comment's `id` field (the `c-…` value) — that is what marks it processed, both for the page's "processing…" banner and for `wait_for_feedback.py`. A comment you decide not to act on still needs a change entry (say why in `title`), or it will keep coming back as pending.
   - `anchor` must match a `data-cf-change` attribute actually present in the HTML.
4. The page polls `history.json`, auto-reloads (scroll preserved), and offers a walkthrough. The banner clears as soon as any `in_response_to` matches a submitted comment.
5. Go back to waiting (Monitor notification in watch mode; the `wait_for_feedback.py` loop in wait mode).

## Pending check

Run on "check feedback", and on setup in a directory that already has a `feedback/` folder:
```
python <skill>/scripts/wait_for_feedback.py <dir> --once
```
Exit 0 → unprocessed comments are printed; tell the user the count and process them (in a setup context, ask first if there are many). Exit 2 → nothing pending. Make sure the server is up (`start_server.py` reuses an existing one), then go back to waiting.

## Stop flow

1. Identify the port: the one you started, or check `curl -s http://localhost:5050/info` (and 5051, 5052, …) for the one whose `artifact_dir` is `<dir>`.
2. `lsof -ti:<port> | xargs kill` (the server exits cleanly on SIGTERM; `kill -9` only if the port isn't freed within a few seconds).
3. Confirm `lsof -i :<port>` is silent. Stop any Monitor / wait loop you had running.

Usually unnecessary: the server exits after 10 min with no browser requests (and, in watch mode, when the agent session ends).

## Update flow

```
python <skill>/scripts/update.py
```
Runs `git pull --ff-only` inside the skill dir if it is a `git clone`. If the skill is vendored into another repo (no `.git` of its own), it says so — update it the way that repo does (e.g. `git subtree pull`).

## Removal flow (clean static copy)

```
python <skill>/scripts/inject.py <dir> --remove
```
Strips both tags from every `*.html`. Leaves `feedback/` alone (delete manually if not wanted).

## Files in this skill

```
<skill>/
├── SKILL.md                    # this file (agent-facing)
├── README.md                   # GitHub-facing docs (human readers)
├── LICENSE
├── lib/
│   ├── feedback.js             # client library: selection + commenting + tour
│   ├── feedback.css            # styles
│   └── server.py               # stdlib-only HTTP server
└── scripts/
    ├── inject.py               # idempotent tag injection / removal
    ├── start_server.py         # start-or-reuse a detached server (wait mode)
    ├── wait_for_feedback.py    # block until unprocessed comments exist
    └── update.py               # git pull --ff-only
```

## Gotchas

- The injected `<link>` and `<script>` use absolute paths `/lib/feedback.css` and `/lib/feedback.js`, which `server.py` routes to the skill's own `lib/`. Opening the HTML file directly in a browser silently skips the widget (the page still renders).
- `history.json` order matters: append, don't prepend.
- `anchor` typos cause "anchor not found" warnings after reload.
- The page shows "No agent picked this up yet" if a batch sits unprocessed for 3 min — in wait mode, keep the wait loop running while the user is commenting.
