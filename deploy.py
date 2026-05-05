"""One-click deploy: commits any pending changes and pushes to GitHub.

The QR code (MamaDay_QR.png) points at the GitHub Pages site for this repo,
which redeploys from `main` automatically. So pushing here = updating the
game that scans of the QR code will load.

Usage: just hit "Run Python File" in your IDE.
"""

import os
import subprocess
import sys
import time

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
TARGET_URL = "https://troygeoghegan.github.io/Operation-Big-Mama/"


def run(cmd, check=True, capture=False):
    """Run a git command in the repo dir; print it for transparency."""
    print(f"  $ {' '.join(cmd)}")
    kwargs = {"cwd": REPO_DIR, "check": check}
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    return subprocess.run(cmd, **kwargs)


def main():
    print(f"Deploying from: {REPO_DIR}\n")

    # 1. Show current state
    status = run(["git", "status", "--short"], capture=True)
    pending = status.stdout.strip()
    if not pending:
        print("Nothing to commit — working tree is clean.")
        print("Pushing anyway in case the local branch is ahead of origin...")
    else:
        print("Pending changes:")
        for line in pending.splitlines():
            print(f"  {line}")
        print()

    # 2. Stage everything except junk (relies on .gitignore for __pycache__)
    run(["git", "add", "-A"])

    # 3. Commit (only if there's anything staged)
    diff = run(["git", "diff", "--cached", "--quiet"], check=False)
    if diff.returncode == 0:
        print("\nNo staged changes — skipping commit.")
    else:
        msg = input("Commit message (blank for auto): ").strip()
        if not msg:
            msg = f"Deploy {time.strftime('%Y-%m-%d %H:%M')}"
        run(["git", "commit", "-m", msg])

    # 4. Push
    print()
    push = run(["git", "push", "origin", "HEAD"], check=False)
    if push.returncode != 0:
        print("\nPush failed. Resolve the issue above and re-run.")
        sys.exit(push.returncode)

    print(f"\nDone. Site will redeploy in ~30-90 seconds at:")
    print(f"  {TARGET_URL}")


if __name__ == "__main__":
    main()
