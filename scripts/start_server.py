"""
Start (or reuse) the feedback server for a directory, fully detached, and
return once it is answering. For agents whose shell commands must return
(e.g. Codex) — Claude Code can instead run lib/server.py as a background task.

    python start_server.py <dir> [--port 5050] [--idle-timeout 600]

- If a server on 5050..5059 already serves <dir>, reuse it.
- Otherwise start one on the first free port in that range (or exactly --port
  if given), in its own session so it survives this command returning. It
  exits on its own after --idle-timeout seconds with no browser requests.
- Server output goes to <dir>/feedback/server.log.

Prints the base URL and the top-level HTML pages. Exit 1 if it can't start.
"""
import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SERVER = SKILL_DIR / "lib" / "server.py"


def server_info(port: int):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/info", timeout=1.5) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("", port))
            return True
        except OSError:
            return False


def report(root: Path, port: int, reused: bool) -> int:
    pages = sorted(p.name for p in root.glob("*.html"))
    print(("REUSED" if reused else "STARTED") + f" feedback server for {root}")
    print(f"URL: http://localhost:{port}/")
    for name in pages:
        print(f"  http://localhost:{port}/{name}")
    print(f"log: {root / 'feedback' / 'server.log'}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir")
    ap.add_argument("--port", type=int, help="use exactly this port (default: first free of 5050-5059)")
    ap.add_argument("--idle-timeout", type=int, default=600)
    args = ap.parse_args()

    root = Path(args.dir).resolve()
    if not root.is_dir():
        print(f"ERROR: {root} is not a directory")
        return 1

    candidates = [args.port] if args.port else list(range(5050, 5060))
    chosen = None
    for port in candidates:
        info = server_info(port)
        if info is not None:
            if Path(info.get("artifact_dir", "")).resolve() == root:
                return report(root, port, reused=True)
            continue  # held by another directory's server
        if port_free(port):
            chosen = port
            break
    if chosen is None:
        print(f"ERROR: no free port in {candidates[0]}-{candidates[-1]}. "
              f"Check with: curl -s http://localhost:<port>/info")
        return 1

    (root / "feedback").mkdir(exist_ok=True)
    log = open(root / "feedback" / "server.log", "a")
    subprocess.Popen(
        [sys.executable, "-u", str(SERVER), str(root), "--port", str(chosen),
         "--idle-timeout", str(args.idle_timeout), "--no-parent-watch"],
        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True,  # own process group: not killed with the agent's shell
        close_fds=True,
    )

    deadline = time.time() + 10
    while time.time() < deadline:
        info = server_info(chosen)
        if info and Path(info.get("artifact_dir", "")).resolve() == root:
            return report(root, chosen, reused=False)
        time.sleep(0.2)
    print(f"ERROR: server did not come up on port {chosen}. Last log lines:")
    try:
        print("".join((root / "feedback" / "server.log").read_text().splitlines(True)[-10:]))
    except OSError:
        pass
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
