"""One-click deploy: builds the web bundle with pygbag and pushes it to
the gh-pages branch — which is what GitHub Pages serves at the URL the
QR code points to.

Workflow:
  1. If there are uncommitted source changes, commits + pushes them to main.
  2. Runs `pygbag --build images/main.py` to produce build/web/.
  3. Clones gh-pages into a temp dir, overlays the new build, commits + pushes.

Usage: open this file in your IDE and hit "Run Python File".
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time

REPO_DIR   = os.path.dirname(os.path.abspath(__file__))
TARGET_URL = "https://troygeoghegan.github.io/Operation-Big-Mama/"


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
    # Copy media that the HTML <video> element fetches by URL — these can't
    # live inside pygbag's virtual FS since the <video> tag runs in the
    # browser context and must read from the same origin.
    images_dir = os.path.join(REPO_DIR, "images")
    for fname in ("Surprise.mov", "Surprise.MOV", "Surprise.mp4"):
        src = os.path.join(images_dir, fname)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(out, fname))
            print(f"  copied {fname} into web bundle")
            break

    # Drop the .tar.gz duplicate — pygbag emits both .apk and .tar.gz with
    # identical contents; the runtime only needs the .apk.
    for entry in os.listdir(out):
        if entry.endswith(".tar.gz"):
            os.remove(os.path.join(out, entry))
            print(f"  pruned {entry} (duplicate of .apk)")

    print(f"Built: {out}\n")
    return out


def cache_bust(web_dir):
    """Append a per-deploy version suffix to the apk bundle filename and
    patch index.html to match. The browser sees a brand-new URL each deploy,
    so any cached old bundle is bypassed. Returns the version string used.
    """
    version = time.strftime("%Y%m%d%H%M%S")
    old_name = "images.apk"
    old_path = os.path.join(web_dir, old_name)
    if not os.path.isfile(old_path):
        return version
    new_name = f"images-{version}.apk"
    shutil.move(old_path, os.path.join(web_dir, new_name))
    idx = os.path.join(web_dir, "index.html")
    if os.path.isfile(idx):
        with open(idx, "r", encoding="utf-8") as f:
            html = f.read()
        html = html.replace(f'"{old_name}"', f'"{new_name}"')
        with open(idx, "w", encoding="utf-8") as f:
            f.write(html)
    return version


def deploy_to_gh_pages(web_dir):
    remote = run(["git", "config", "--get", "remote.origin.url"], capture=True).stdout.strip()

    with tempfile.TemporaryDirectory(prefix="ghp-deploy-") as tmp:
        run(["git", "clone", "--branch", "gh-pages", "--single-branch", remote, tmp])

        # Remove stale versioned bundles from gh-pages so it doesn't bloat over
        # time. (Static assets like nodo.mp4 / nodo_logo.png / favicon.png stay.)
        for entry in os.listdir(tmp):
            if entry == ".git":
                continue
            if entry.startswith("images") and (entry.endswith(".apk") or entry.endswith(".tar.gz")):
                os.remove(os.path.join(tmp, entry))

        # Overlay the new build onto gh-pages (don't wipe other files —
        # preserves manually-uploaded assets that the game loads by URL).
        for entry in os.listdir(web_dir):
            src = os.path.join(web_dir, entry)
            dst = os.path.join(tmp, entry)
            if os.path.isdir(src):
                if os.path.isdir(dst):
                    shutil.rmtree(dst)
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

        run(["git", "add", "-A"], cwd=tmp)
        diff = run(["git", "diff", "--cached", "--quiet"], cwd=tmp, check=False)
        if diff.returncode == 0:
            print("No changes in built bundle. Skipping gh-pages commit.")
            return
        run(["git", "commit", "-m", f"Deploy {time.strftime('%Y-%m-%d %H:%M')}"], cwd=tmp)
        run(["git", "push", "origin", "gh-pages"], cwd=tmp)


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
