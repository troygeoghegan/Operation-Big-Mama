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


def cache_bust(web_dir):
    """Append a per-deploy version suffix to the python bundle filenames
    (images.apk / images.tar.gz) and patch index.html to match. The browser
    sees a brand-new URL each deploy, so any cached old bundle is bypassed.
    Returns the version string used.
    """
    version = time.strftime("%Y%m%d%H%M%S")
    renames = []
    for old_name in ("images.apk", "images.tar.gz"):
        old_path = os.path.join(web_dir, old_name)
        if os.path.isfile(old_path):
            new_name = old_name.replace("images.", f"images-{version}.")
            shutil.move(old_path, os.path.join(web_dir, new_name))
            renames.append((old_name, new_name))
    idx = os.path.join(web_dir, "index.html")
    if os.path.isfile(idx) and renames:
        with open(idx, "r", encoding="utf-8") as f:
            html = f.read()
        for old, new in renames:
            html = html.replace(f'"{old}"', f'"{new}"')
        with open(idx, "w", encoding="utf-8") as f:
            f.write(html)
    return version


def deploy_to_gh_pages(web_dir):
    # Wipe any leftover worktree from a prior run
    if os.path.isdir(WORKTREE_DIR):
        run(["git", "worktree", "remove", "--force", WORKTREE_DIR], check=False)

    # Prune stale refs first — origin/gh-pages may have been deleted server-side
    run(["git", "fetch", "--prune", "origin"])

    ls = run(["git", "ls-remote", "--heads", "origin", "gh-pages"], capture=True)
    has_remote = bool(ls.stdout.strip())
    has_local = run(
        ["git", "show-ref", "--verify", "--quiet", "refs/heads/gh-pages"],
        check=False,
    ).returncode == 0

    if has_remote:
        # -B resets local gh-pages to origin/gh-pages and checks it out
        run(["git", "worktree", "add", "-B", "gh-pages", WORKTREE_DIR, "origin/gh-pages"])
    elif has_local:
        # Remote branch is gone but we still have local history — push will recreate it
        print("origin/gh-pages missing; basing worktree on local gh-pages branch.")
        run(["git", "worktree", "add", "-B", "gh-pages", WORKTREE_DIR, "gh-pages"])
    else:
        # First-ever deploy: create an orphan gh-pages branch
        print("No gh-pages branch found; creating a fresh orphan branch.")
        orphan = run(
            ["git", "worktree", "add", "--orphan", "-b", "gh-pages", WORKTREE_DIR],
            check=False,
        )
        if orphan.returncode != 0:
            # Fallback for git < 2.42 which lacks --orphan on worktree add
            run(["git", "worktree", "add", "--detach", WORKTREE_DIR, "HEAD"])
            run(["git", "checkout", "--orphan", "gh-pages"], cwd=WORKTREE_DIR)
            run(["git", "rm", "-rf", "."], cwd=WORKTREE_DIR, check=False)

    # Remove stale versioned bundles from gh-pages so it doesn't bloat over
    # time. (Static assets like nodo.mp4 / nodo_logo.png / favicon.png stay.)
    for entry in os.listdir(WORKTREE_DIR):
        if entry == ".git":
            continue
        if entry.startswith("images") and (entry.endswith(".apk") or entry.endswith(".tar.gz")):
            os.remove(os.path.join(WORKTREE_DIR, entry))

    # Overlay the new build onto gh-pages (don't wipe other files —
    # preserves manually-uploaded assets that the game loads by URL).
    for entry in os.listdir(web_dir):
        src = os.path.join(web_dir, entry)
        dst = os.path.join(WORKTREE_DIR, entry)
        if os.path.isdir(src):
            if os.path.isdir(dst):
                shutil.rmtree(dst)
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
    version = cache_bust(web_dir)
    print(f"Cache-busted bundle version: {version}\n")
    deploy_to_gh_pages(web_dir)
    print(f"\nDone. Live in ~30-90 seconds at:\n  {TARGET_URL}")
    print("Refresh the page on your phone to see the latest.")


if __name__ == "__main__":
    main()
