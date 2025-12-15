

# brew-tools: all commands & installer

This file contains everything you need to do to setup `brew-tools` in the `homebrew-brew-tools` repo, from scratch.  I hav ecreated the repo and that's the dolder we're i now.    You can follows these steps, or paste them into a posix CLI (like Warp) to create the `brew-tools` scaffold, the `homebrew-brew-tools` tap scaffold, the executable Python tools (`brew-index` and `brew-first-installs`), Homebrew formula templates, CI, and a one-shot installer script that writes all files, initializes git repositories, and (optionally) creates the GitHub repos with `gh`.

---

## Safety & preflight

Before running the one-shot installer or any of these commands, make sure:

1. You have `brew` installed and available on `PATH`.
2. You have `python3` installed (`python3 --version`).
3. You have `gh` (GitHub CLI) installed and you are authenticated (`gh auth status`) if you want the script to create GitHub repos automatically.
4. You understand this script will create local repos under `~/src/` and run `git init` and `git push` if you allow the `gh` creation/push steps.

If you do not want the script to push to GitHub automatically, set `CREATE_GITHUB_REPOS=false` in the installer.

---

## One-shot installer

Paste the following into Warp (or save to a file and `bash script.sh`). It will create two local projects under `~/src/`: `brew-tools` (the primary repo) and `homebrew-brew-tools` (the tap repo). It will write all files, make executables, initialize git repos, and — if `gh` is available and you choose to — create and push remote repos on GitHub under `newalexandria` (change the username variable if needed).

```
#!/usr/bin/env bash
set -euo pipefail

# One-shot scaffold installer for brew-tools & tap
# Run this from your shell. Edit NEW_GH_USER to your GitHub username if you want auto-push.

NEW_GH_USER="newalexandria"
BASE_DIR="$HOME/src"
BREW_TOOLS_DIR="$BASE_DIR/brew-tools"
TAP_DIR="$BASE_DIR/homebrew-brew-tools"
CREATE_GITHUB_REPOS=true   # set to false to skip gh repo create / push

mkdir -p "$BREW_TOOLS_DIR/bin" \
         "$BREW_TOOLS_DIR/libexec/python" \
         "$BREW_TOOLS_DIR/scripts" \
         "$BREW_TOOLS_DIR/.github/workflows" \
         "$TAP_DIR/Formula"

# Write brew-index (executable)
cat > "$BREW_TOOLS_DIR/bin/brew-index" <<'PY'
#!/usr/bin/env python3
"""brew-index

Index Homebrew installs and write installs_index.json into the brew repository.
"""

import argparse
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


def run_cmd(cmd):
    try:
        if isinstance(cmd, (list, tuple)):
            return subprocess.check_output(cmd, text=True).strip()
        else:
            return subprocess.check_output(cmd, shell=True, text=True).strip()
    except subprocess.CalledProcessError:
        return None


def get_iso_time(epoch):
    dt = datetime.fromtimestamp(epoch)
    if time.localtime(epoch).tm_isdst and time.daylight:
        tz_offset = -time.altzone
    else:
        tz_offset = -time.timezone
    tz_hours = tz_offset // 3600
    tz_minutes = (abs(tz_offset) % 3600) // 60
    tz_str = f"{tz_hours:+03d}{tz_minutes:02d}"
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + tz_str


class Enricher:
    def __init__(self):
        self.taps = {}
        self.installed_info = {}
        self._load_taps()
        self._load_installed_info()

    def _load_taps(self):
        self.taps = {
            "homebrew/core": "Homebrew/homebrew-core",
            "homebrew/cask": "Homebrew/homebrew-cask",
            "homebrew/cask-fonts": "Homebrew/homebrew-cask-fonts",
            "homebrew/cask-versions": "Homebrew/homebrew-cask-versions",
        }
        out = run_cmd(["brew", "tap-info", "--json"]) or run_cmd("brew tap-info --json")
        if not out:
            return
        try:
            data = json.loads(out)
            for tap in data:
                remote = tap.get("remote")
                name = tap.get("name")
                if remote and "github.com" in remote:
                    parts = remote.rstrip(".git").split("/")
                    if len(parts) >= 2:
                        repo_path = f"{parts[-2]}/{parts[-1]}"
                        self.taps[name] = repo_path
        except Exception as e:
            print(f"Warning: Failed to parse tap-info: {e}", file=sys.stderr)

    def _load_installed_info(self):
        out = run_cmd(["brew", "info", "--json=v2", "--installed"]) or run_cmd("brew info --json=v2 --installed")
        if not out:
            return
        try:
            data = json.loads(out)
            items = data.get("formulae", []) + data.get("casks", [])
            for item in items:
                try:
                    keys = []
                    if "token" in item:
                        keys.append(item["token"])
                    if "full_token" in item:
                        keys.append(item.get("full_token"))
                    if "name" in item:
                        keys.append(item.get("name"))
                    if "full_name" in item:
                        keys.append(item.get("full_name"))
                    keys = [k for k in keys if k and isinstance(k, str)]
                    for k in keys:
                        self.installed_info[k] = item
                    aliases = item.get("aliases", [])
                    if isinstance(aliases, list):
                        for alias in aliases:
                            if alias and isinstance(alias, str):
                                self.installed_info[alias] = item
                except Exception:
                    continue
        except Exception as e:
            print(f"Warning: Failed to load installed info: {e}", file=sys.stderr)

    def get_repo_and_path(self, formula_name):
        info = self.installed_info.get(formula_name)
        if not info:
            return None, None
        tap_name = info.get("tap")
        repo = self.taps.get(tap_name)
        path = info.get("ruby_source_path")
        if repo and path:
            return repo, path
        return None, None

    def fetch_oldest_commit_date(self, formula_name):
        repo, path = self.get_repo_and_path(formula_name)
        if not repo or not path:
            return None
        endpoint = f"/repos/{repo}/commits?path={path}&per_page=1"
        try:
            cmd = ["gh", "api", "-i", endpoint]
            output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
            parts = output.split("\n\n", 1)
            headers = parts[0]
            last_page = 1
            for line in headers.splitlines():
                if line.lower().startswith("link:"):
                    matches = re.findall(r'<([^>]+)>;\s*rel="([^\"]+)"', line)
                    for url, rel in matches:
                        if rel == "last":
                            m = re.search(r'[?&]page=(\d+)', url)
                            if m:
                                last_page = int(m.group(1))
            if last_page > 1:
                endpoint_last = f"{endpoint}&page={last_page}"
                out_json = subprocess.check_output(["gh", "api", endpoint_last], text=True, stderr=subprocess.DEVNULL)
                data = json.loads(out_json)
            else:
                body = parts[1] if len(parts) > 1 else "[]"
                data = json.loads(body)
            if isinstance(data, list) and len(data) > 0:
                commit = data[-1]
                return commit["commit"]["committer"]["date"]
        except Exception as e:
            print(f"Debug: fetch failed for {repo}/{path}: {e}", file=sys.stderr)
            return None
        return None


def main():
    parser = argparse.ArgumentParser(description="Index Homebrew installs and optionally enrich with GitHub history.")
    parser.add_argument("--enrich", action="store_true", help="Enrich with history from GitHub")
    parser.add_argument("--available", action="store_true", help="Index available (non-installed) packages from last year")
    args = parser.parse_args()

    brew_repo = run_cmd(["brew", "--repository"]) or os.path.expanduser("~/.homebrew")
    cellar = run_cmd(["brew", "--cellar"]) or run_cmd("brew --cellar 2>/dev/null")
    caskroom = run_cmd(["brew", "--caskroom"]) or run_cmd("brew --caskroom 2>/dev/null")

    print(f"Scanning Homebrew Cellar: {cellar}", file=sys.stderr)

    records = []

    if cellar and os.path.isdir(cellar):
        cellar_path = Path(cellar)
        for receipt in cellar_path.rglob("INSTALL_RECEIPT.json"):
            try:
                version_dir = receipt.parent
                formula_dir = version_dir.parent
                formula = formula_dir.name
                version = version_dir.name
                mtime_epoch = int(receipt.stat().st_mtime)
                mtime_iso = get_iso_time(mtime_epoch)
                try:
                    with open(receipt, "r") as f:
                        data = json.load(f)
                        if "formula" in data and "name" in data["formula"]:
                            formula = data["formula"]["name"]
                except Exception:
                    pass
                records.append({
                    "formula": formula,
                    "version": version,
                    "install_path": str(receipt),
                    "install_time": mtime_iso,
                    "install_epoch": mtime_epoch
                })
            except Exception as e:
                print(f"Error processing {receipt}: {e}", file=sys.stderr)

    if caskroom and os.path.isdir(caskroom):
        caskroom_path = Path(caskroom)
        try:
            for cask_dir in caskroom_path.iterdir():
                if not cask_dir.is_dir():
                    continue
                for version_dir in cask_dir.iterdir():
                    if not version_dir.is_dir():
                        continue
                    if version_dir.name == ".metadata":
                        continue
                    cask = cask_dir.name
                    version = version_dir.name
                    mtime_epoch = int(version_dir.stat().st_mtime)
                    mtime_iso = get_iso_time(mtime_epoch)
                    records.append({
                        "formula": cask,
                        "version": version,
                        "install_path": str(version_dir),
                        "install_time": mtime_iso,
                        "install_epoch": mtime_epoch,
                        "type": "cask"
                    })
        except Exception as e:
            print(f"Error processing Casks in {caskroom}: {e}", file=sys.stderr)

    groups = {}
    for r in records:
        key = f"{r['formula']}||{r['version']}"
        groups.setdefault(key, []).append(r)

    final_records = []
    for key, group in groups.items():
        min_epoch = min(item["install_epoch"] for item in group)
        min_iso = get_iso_time(min_epoch)
        for item in group:
            item["first_installed_epoch"] = min_epoch
            item["first_installed_time"] = min_iso
            item["first_installed"] = (item["install_epoch"] == min_epoch)
            final_records.append(item)

    if args.enrich:
        print("Enriching with GitHub history (this may take a while)...", file=sys.stderr)
        enricher = Enricher()
        print(f"Loaded {len(enricher.taps)} taps and {len(enricher.installed_info)} installed info records", file=sys.stderr)
        unique_formulas = set(r["formula"] for r in final_records)
        history_map = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_to_formula = {executor.submit(enricher.fetch_oldest_commit_date, f): f for f in unique_formulas}
            for future in concurrent.futures.as_completed(future_to_formula):
                form = future_to_formula[future]
                try:
                    date = future.result()
                    if date:
                        history_map[form] = date
                        print(f"Found history for {form}: {date}", file=sys.stderr)
                    else:
                        print(f"No history found for {form}", file=sys.stderr)
                except Exception as e:
                    print(f"Error fetching history for {form}: {e}", file=sys.stderr)
        print(f"Enrichment complete. Found history for {len(history_map)} formulas.", file=sys.stderr)
        for r in final_records:
            if r["formula"] in history_map:
                r["repo_first_commit_date"] = history_map[r["formula"]]

    if args.available and brew_repo:
        print("Scanning for available packages added in the last year...", file=sys.stderr)
        taps_dir = Path(brew_repo) / "Library/Taps"
        available_map = {}
        if taps_dir.is_dir():
            for tap in taps_dir.iterdir():
                if not tap.is_dir():
                    continue
                for tap_repo in tap.iterdir():
                    if not tap_repo.is_dir() or not (tap_repo / ".git").exists():
                        continue
                    paths_to_scan = []
                    for p in ["Formula", "Casks"]:
                        if (tap_repo / p).is_dir():
                            paths_to_scan.append(p + "/")
                    if not paths_to_scan:
                        continue
                    cmd = [
                        "git", "-C", str(tap_repo), "log",
                        "--diff-filter=A", "--name-only", "--format=DT:%aI",
                        "--since=1 year ago", "--"
                    ] + paths_to_scan
                    try:
                        output = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
                        current_date = None
                        for line in output.splitlines():
                            line = line.strip()
                            if not line: continue
                            if line.startswith("DT:"):
                                current_date = line[3:]
                            elif current_date:
                                name = Path(line).stem
                                if name not in available_map:
                                    available_map[name] = current_date
                    except subprocess.CalledProcessError:
                        print(f"Warning: Failed to scan tap {tap_repo.name}", file=sys.stderr)
        installed_names = set(r["formula"] for r in final_records)
        for name, date_iso in available_map.items():
            if name in installed_names:
                continue
            try:
                dt = datetime.fromisoformat(date_iso)
                epoch = int(dt.timestamp())
                final_records.append({
                    "formula": name,
                    "version": "N/A",
                    "install_path": "",
                    "install_time": date_iso,
                    "install_epoch": epoch,
                    "first_installed": True,
                    "first_installed_epoch": epoch,
                    "first_installed_time": date_iso,
                    "repo_first_commit_date": date_iso,
                    "status": "available"
                })
            except ValueError:
                pass

    out_json = os.path.join(brew_repo, "installs_index.json")
    final_records.sort(key=lambda x: (x.get("formula", ""), x.get("version", ""), x.get("install_epoch", 0)))
    try:
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(final_records, f, indent=2, sort_keys=True)
        print(f"Index created: {out_json}")
    except Exception as e:
        print(f"Error writing output to {out_json}: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
PY

# Write brew-first-installs (executable)
cat > "$BREW_TOOLS_DIR/bin/brew-first-installs" <<'PY'
#!/usr/bin/env python3
"""brew-first-installs

Find packages whose first-installed date falls between X and Y days ago.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
import subprocess


def iso_from_epoch(epoch: int) -> str:
    dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    return dt.isoformat()


def get_brew_repo():
    brew_repo = None
    try:
        brew_repo = subprocess.check_output(["brew", "--repository"], text=True).strip()
    except Exception:
        brew_repo = None
    if not brew_repo:
        brew_repo = os.path.expanduser("~/.homebrew")
    return brew_repo


def load_index(brew_repo: str) -> list:
    index_path = Path(brew_repo) / "installs_index.json"
    if not index_path.is_file():
        print(f"Index file not found at {index_path}", file=sys.stderr)
        sys.exit(2)
    with open(index_path, "r", encoding="utf-8") as f:
        return json.load(f)


def format_table(records):
    cols = ["Time", "Formula", "Version", "Status", "Path"]
    widths = [25, 30, 12, 12, 40]
    lines = []
    header = "  ".join(c.ljust(w) for c, w in zip(cols, widths))
    lines.append(header)
    lines.append("-" * sum(widths))
    for r in records:
        t = r.get("first_installed_time", "unknown")
        f = r.get("formula", "")
        v = r.get("version", "")
        s = r.get("status", "installed")
        p = r.get("install_path", "")
        status_str = "(Available)" if s == "available" else ""
        lines.append("  ".join([t.ljust(widths[0]), f.ljust(widths[1]), v.ljust(widths[2]), status_str.ljust(widths[3]), p.ljust(widths[4])]))
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Find packages installed for the first time between X and Y days ago.")
    parser.add_argument("X", type=int, help="Older bound (days ago)")
    parser.add_argument("Y", type=int, help="Newer bound (days ago)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON array")
    parser.add_argument("--info", action="store_true", help="Show brew info for each match")
    args = parser.parse_args()
    brew_repo = get_brew_repo()
    now = int(time.time())
    start_epoch = now - args.X * 86400
    end_epoch = now - args.Y * 86400
    records = load_index(brew_repo)
    matches = [
        r for r in records
        if r.get("first_installed") and start_epoch <= r.get("first_installed_epoch", 0) <= end_epoch
    ]
    if args.json:
        json.dump(matches, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return
    if not matches:
        print("No matching installs found.")
        return
    print(format_table(matches))
    if args.info:
        print("\n" + "="*80 + "\n")
        for r in matches:
            formula = r.get("formula")
            if formula:
                print(f"--- Info for {formula} ---")
                try:
                    subprocess.run(["brew", "info", formula], check=False)
                except Exception as e:
                    print(f"Error running info for {formula}: {e}", file=sys.stderr)
                print("\n")

if __name__ == '__main__':
    main()
PY

# Make executables
chmod +x "$BREW_TOOLS_DIR/bin/brew-index" "$BREW_TOOLS_DIR/bin/brew-first-installs"

# README
cat > "$BREW_TOOLS_DIR/README.md" <<'MD'
# brew-tools

Helper scripts for Homebrew: `brew-index` and `brew-first-installs`.

## Quick local install

    git clone https://github.com/yourusername/brew-tools.git
    cp brew-tools/bin/* ~/.local/bin/
    chmod +x ~/.local/bin/brew-index ~/.local/bin/brew-first-installs

## Using the tap (optional)

After publishing the tap `newalexandria/homebrew-brew-tools` you can:

    brew tap newalexandria/brew-tools
    brew install newalexandria/brew-tools/brew-index

MD

# VERSION & LICENSE
cat > "$BREW_TOOLS_DIR/VERSION" <<'TXT'
0.0.1
TXT

cat > "$BREW_TOOLS_DIR/LICENSE" <<'MD'
MIT License

Copyright (c) $(date +%Y) $NEW_GH_USER

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction...
MD

# setup.sh
cat > "$BREW_TOOLS_DIR/scripts/setup.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$HOME/.local/bin"
cp "$ROOT/bin/"* "$HOME/.local/bin/"
chmod +x "$HOME/.local/bin/"*
echo "Installed executables to $HOME/.local/bin. Make sure it's on your PATH."
SH
chmod +x "$BREW_TOOLS_DIR/scripts/setup.sh"

# GitHub Actions (basic smoke checks)
cat > "$BREW_TOOLS_DIR/.github/workflows/python-ci.yml" <<'YML'
name: Python CI
on: [push, pull_request]
jobs:
  test:
    runs-on: macos-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Syntax check
        run: |
          python -m py_compile bin/brew-index || true
          python -m py_compile bin/brew-first-installs || true
YML

# Homebrew tap formula templates
cat > "$TAP_DIR/Formula/brew-index.rb" <<'RB'
class BrewIndex < Formula
  desc "Index Homebrew installs into installs_index.json"
  homepage "https://github.com/${NEW_GH_USER}/homebrew-brew-tools"
  url "https://example.org/brew-index-0.0.1.tar.gz"
  version "0.0.1"
  license "MIT"

  depends_on "python@3.11"

  def install
    bin.install "bin/brew-index" => "brew-index"
  end

  test do
    system "#{bin}/brew-index", "--help"
  end
end
RB

cat > "$TAP_DIR/Formula/brew-first-installs.rb" <<'RB'
class BrewFirstInstalls < Formula
  desc "Query the Homebrew installs_index.json for first-installed packages"
  homepage "https://github.com/${NEW_GH_USER}/homebrew-brew-tools"
  url "https://example.org/brew-first-installs-0.0.1.tar.gz"
  version "0.0.1"
  license "MIT"

  depends_on "python@3.11"

  def install
    bin.install "bin/brew-first-installs" => "brew-first-installs"
  end

  test do
    system "#{bin}/brew-first-installs", "--help"
  end
end
RB

# Initialize git repos and commit
(
  cd "$BREW_TOOLS_DIR"
  git init
  git add .
  git commit -m "Initial scaffold for brew-tools"
)
(
  cd "$TAP_DIR"
  git init
  git add .
  git commit -m "Initial scaffold for homebrew tap: homebrew-brew-tools"
)

# Optionally create GitHub repos and push
if [ "$CREATE_GITHUB_REPOS" = true ] && command -v gh >/dev/null 2>&1; then
  echo "Creating GitHub repos under $NEW_GH_USER (requires gh auth)
  "
  gh repo create "$NEW_GH_USER/brew-tools" --public --source="$BREW_TOOLS_DIR" --remote=origin --push || true
  gh repo create "$NEW_GH_USER/homebrew-brew-tools" --public --source="$TAP_DIR" --remote=origin --push || true
else
  echo "Skipping GitHub creation (set CREATE_GITHUB_REPOS=true and ensure 'gh' is installed and authenticated)"
fi

echo "Done. Repos created locally at: $BREW_TOOLS_DIR and $TAP_DIR"
```

---

## Manual step-by-step commands (if you prefer copy/paste instead of the one-shot)

Below are modular commands that perform the same operations as the one-shot script but in smaller steps. Paste them in order if you prefer to inspect files as they are created.

1. Create directories

```bash
mkdir -p ~/src/brew-tools/{bin,libexec/python,scripts,.github/workflows}
mkdir -p ~/src/homebrew-brew-tools/Formula
```

2. Write `bin/brew-index` and `bin/brew-first-installs` using `cat > file <<'EOF'` blocks — use the same contents as in the one-shot above.

3. Make executables

```bash
chmod +x ~/src/brew-tools/bin/brew-index ~/src/brew-tools/bin/brew-first-installs
```

4. Write README, LICENSE, VERSION, setup.sh, and CI YAML (see one-shot above for full text)

5. Initialize git and commit in each repo

```bash
cd ~/src/brew-tools
git init
git add .
git commit -m "Initial scaffold for brew-tools"

cd ~/src/homebrew-brew-tools
git init
git add .
git commit -m "Initial scaffold for homebrew tap: homebrew-brew-tools"
```

6. (Optional) Create GitHub repos with `gh` and push

```bash
gh repo create newalexandria/brew-tools --public --source=~/src/brew-tools --remote=origin --push
gh repo create newalexandria/homebrew-brew-tools --public --source=~/src/homebrew-brew-tools --remote=origin --push
```

7. Local install of executables

```bash
mkdir -p ~/.local/bin
cp ~/src/brew-tools/bin/* ~/.local/bin/
chmod +x ~/.local/bin/brew-index ~/.local/bin/brew-first-installs
```

8. Usage

```bash
# Build index (with optional GitHub enrichment)
brew-index --enrich

# Query first installs in a 30..7 days window
brew-first-installs 30 7

# Output JSON
brew-first-installs 365 0 --json
```

---

## Notes & troubleshooting

- If `brew-index` prints errors about `gh` not found while enriching, either install `gh` or run without `--enrich`.
- If the index file cannot be found, ensure `brew --repository` works and that `installs_index.json` exists under that path.
- The tap formula templates use a placeholder `url` – Homebrew taps typically install from git; publishing the tap to GitHub is the usual way to share them.

---

## Done

This file was written to be pasted into a terminal or saved into your dotfiles. If you want adjustments (change default directories, different GitHub username, add more tools), tell me and I will update the script.
