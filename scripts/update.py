"""
Update the make-pages-interactive skill from GitHub.

Runs `git pull --ff-only` inside the skill directory. Requires the skill to
have been installed via `git clone` (we check for .git/).

Usage:
    python update.py
"""
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
REPO_URL = "https://github.com/paraschopra/make-pages-interactive"


def main() -> int:
    git_dir = SKILL_DIR / ".git"
    if not git_dir.exists():
        parent_repo = subprocess.run(
            ["git", "-C", str(SKILL_DIR), "rev-parse", "--show-toplevel"],
            capture_output=True, text=True,
        )
        if parent_repo.returncode == 0:
            top = parent_repo.stdout.strip()
            prefix = SKILL_DIR.relative_to(top) if SKILL_DIR.is_relative_to(top) else SKILL_DIR.name
            print(f"This skill is vendored inside another git repo ({top}), not its own clone.")
            print("Update it from that repo, e.g. if it was added as a git subtree:")
            print(f"  cd {top} && git subtree pull --prefix={prefix} {REPO_URL}.git main")
            return 1
        print("ERROR: skill is not a git checkout — cannot auto-update.")
        print(f"  Expected: {git_dir}")
        print()
        print("To enable auto-update, reinstall via git clone:")
        print(f"  rm -rf {SKILL_DIR}")
        print(f"  git clone {REPO_URL} {SKILL_DIR}")
        return 1

    print(f"Checking for updates in {SKILL_DIR} ...")
    result = subprocess.run(
        ["git", "-C", str(SKILL_DIR), "pull", "--ff-only"],
        capture_output=True, text=True,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        print("\nUpdate failed. Resolve manually:")
        print(f"  cd {SKILL_DIR} && git status")
        return result.returncode

    if "Already up to date" in result.stdout:
        print("\nSkill is up to date.")
    else:
        print("\nSkill updated. New invocations will use the latest lib/.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
