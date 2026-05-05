"""One-click deploy: builds the web bundle with pygbag and pushes it to
the gh-pages branch — which is what GitHub Pages serves at the URL the
QR code points to.

Workflow:
  1. If there are uncommitted source changes, commits + pushes them to main.
  2. Runs `pygbag --build images/main.py` to produce build/web/.
  3. Copies the built bundle into a temporary git worktree on gh-pages.
  4. Commits + pushes gh-pages.
  5. Cleans up the worktree.

Usage: open this file in your IDE and hit "Run Python File".
"""

import os
import shutil
import subprocess
import sys
import time

REPO_DIR     = os.path.dirname(os.path.abspath(__file__))
TARGET_URL   = "https://troygeoghegan.github.io/Operation-Big-Mama/"
WORKTREE_DIR = os.path.join(REPO_DIR, ".gh-pages-worktree")


def run(cmd, cwd=None, check=True, capture=False):
    cwd = cwd or REPO_DIR
    print(f"  $ {' '.join(map(str, cmd))}")
    kw = {"cwd": cwd, "check": check}
    if capture:
        kw["capture_output"] = True
        kw["text"] = True
    return subprocess.run(cmd, **kw)


def find_build_web():
    """pygbag may emit build/web/ next to either the script or the cwd."""
    for candidate in (
        os.path.join(REPO_DIR, "images", "build", "web"),
        os.path.join(REPO_DIR, "build", "web"),
    ):
        if os.path.isdir(candidate) and os.path.isfile(os.path.join(candidate, "index.html")):
            return candidate
    return None


def commit_source_if_dirty():
    status = run(["git", "status", "--short"], capture=True)
    pending = [ln for ln in status.stdout.splitlines() if ln.strip()]
    if not pending:
        print("No source changes to commit.\n")
        return
    print("Source changes:")
    for line in pending:
        print(f"  {line}")
    msg = input("\nCommit message (blank for auto): ").strip()
    if not msg:
        msg = f"Update {time.strftime('%Y-%m-%d %H:%M')}"
    run(["git", "add", "-A"])
    run(["git", "commit", "-m", msg])
    run(["git", "push", "origin", "main"])
    print()


def build_web():
    print("Building web bundle (pygbag)...")
    # Don't pre-clean — pygbag's incremental build breaks if web/ is wiped
    # while web-cache/ remains. It overwrites the output files in place.
    run([sys.executable, "-m", "pygbag", "--build", "images/main.py"])
    out = find_build_web()
    if not out:
        print("ERROR: pygbag finished but no build/web/index.html found.")
        print("       First run needs internet (pygbag fetches a CDN template).")
        sys.exit(1)
    print(f"Built: {out}\n")
    return out


def deploy_to_gh_pages(web_dir):
    # Wipe any leftover worktree from a prior run
    if os.path.isdir(WORKTREE_DIR):
        run(["git", "worktree", "remove", "--force", WORKTREE_DIR], check=False)

    run(["git", "fetch", "origin", "gh-pages"])
    # -B resets local gh-pages to origin/gh-pages and checks it out
    run(["git", "worktree", "add", "-B", "gh-pages", WORKTREE_DIR, "origin/gh-pages"])

    # Wipe worktree contents (preserve .git pointer) then copy the new build in
    for entry in os.listdir(WORKTREE_DIR):
        if entry == ".git":
            continue
        p = os.path.join(WORKTREE_DIR, entry)
        if os.path.isdir(p):
            shutil.rmtree(p)
        else:
            os.remove(p)
    for entry in os.listdir(web_dir):
        src = os.path.join(web_dir, entry)
        dst = os.path.join(WORKTREE_DIR, entry)
        if os.path.isdir(src):
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)

    run(["git", "add", "-A"], cwd=WORKTREE_DIR)
    diff = run(["git", "diff", "--cached", "--quiet"], cwd=WORKTREE_DIR, check=False)
    if diff.returncode == 0:
        print("No changes in built bundle. Skipping gh-pages commit.")
    else:
        run(["git", "commit", "-m", f"Deploy {time.strftime('%Y-%m-%d %H:%M')}"], cwd=WORKTREE_DIR)
        run(["git", "push", "origin", "gh-pages"], cwd=WORKTREE_DIR)

    run(["git", "worktree", "remove", "--force", WORKTREE_DIR])


def main():
    print(f"Deploying from: {REPO_DIR}\n")
    commit_source_if_dirty()
    web_dir = build_web()
    deploy_to_gh_pages(web_dir)
    print(f"\nDone. Live in ~30-90 seconds at:\n  {TARGET_URL}")
    print("Refresh the page on your phone to see the latest.")


if __name__ == "__main__":
    main()
