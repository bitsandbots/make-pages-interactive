"""
Block until there is unprocessed feedback in <dir>/feedback/inbox.jsonl, then
print it. For agents without a file-watch tool (e.g. Codex); also handy for
"is anything pending?" checks in any agent.

    python wait_for_feedback.py <dir> [--timeout 300]   # wait up to 5 min
    python wait_for_feedback.py <dir> --once            # check now, don't wait

A comment is "unprocessed" when its `id` does not appear in any
`changes[*].in_response_to` in feedback/history.json.

Output: a JSON object {"pending": [ {comment fields..., "page_url",
"submitted_at"} ... ]}. Exit 0 if there is pending feedback, 2 if none
(timed out / nothing pending), 1 on error.
"""
import argparse
import json
import sys
import time
from pathlib import Path


def processed_ids(history_path: Path) -> set:
    try:
        history = json.loads(history_path.read_text() or "[]")
    except (OSError, json.JSONDecodeError):
        return set()  # mid-write or missing; treat as nothing processed yet
    done = set()
    for batch in history if isinstance(history, list) else []:
        for ch in batch.get("changes") or []:
            done.update(ch.get("in_response_to") or [])
    return done


def pending_comments(fb: Path) -> list:
    done = processed_ids(fb / "history.json")
    out = []
    try:
        lines = (fb / "inbox.jsonl").read_text().splitlines()
    except OSError:
        return out
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            batch = json.loads(line)
        except json.JSONDecodeError:
            continue  # partial trailing line still being written
        for c in batch.get("comments") or []:
            if c.get("id") and c["id"] not in done:
                out.append(dict(c, page_url=batch.get("page_url"),
                                submitted_at=batch.get("submitted_at")))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir")
    ap.add_argument("--timeout", type=float, default=300, help="seconds to wait (default 300)")
    ap.add_argument("--once", action="store_true", help="report what's pending now; don't wait")
    ap.add_argument("--poll", type=float, default=1.0, help="poll interval in seconds")
    args = ap.parse_args()

    fb = Path(args.dir).resolve() / "feedback"
    if not (fb / "inbox.jsonl").exists():
        print(f"ERROR: {fb / 'inbox.jsonl'} not found — run scripts/inject.py on the directory first")
        return 1

    deadline = time.time() + (0 if args.once else args.timeout)
    while True:
        pending = pending_comments(fb)
        if pending:
            # Give the user's browser a moment in case a multi-comment batch is
            # landing; then report everything pending.
            time.sleep(0.5)
            print(json.dumps({"pending": pending_comments(fb)}, indent=2))
            return 0
        if time.time() >= deadline:
            print(json.dumps({"pending": []}))
            print("no new feedback" + ("" if args.once else f" after {args.timeout:.0f}s"), file=sys.stderr)
            return 2
        time.sleep(args.poll)


if __name__ == "__main__":
    raise SystemExit(main())
