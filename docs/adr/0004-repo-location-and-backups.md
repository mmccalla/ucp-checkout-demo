# ADR 0004: Repository location, Git remote and bundle backups

- Status: Accepted (approved by the project owner on 2026-10-24, 22:47 BST).
- Date: 2026-10-24.

## Context

1. At approximately 22:43 BST the box started again (`uptime -s` = `2026-10-24 22:43:05`).
2. After the restart, all of `<old build folder>/` was missing. This folder held the Git repository with S0 and S1, and the S2 work that was not committed.
3. Other folders of `<project folder>` were not lost. Evidence: `<evidence folder>/rebuild/loss-cause.log`.

## Findings (what survived and what did not)

| Path | Result |
|---|---|
| `<box tools folder>/ucp/.git`, `<box tools folder>/samples/.git`, `<box tools folder>/ucp-schema/.git` | Survived |
| `src/gh-*/.git`, `<tags folder>/*/.git`, other `<box folder>/*/.git` | Survived |
| `<box tools folder>/caddy-bin/caddy` and the 18 MB Caddy archive | Survived |
| `<old build folder>/` (all) | Lost |
| `<box tools folder>/ucp-schema/target/` (Rust build output, not in `build/`) | Lost |
| Folders named `build`, `target`, `.run`, `.venv`, `node_modules`, `__pycache__`, `dist` in the box folders (depth 8) | None found |
| `~/.cache/ms-playwright`, `~/.cargo/registry` | Lost |

## Cause

INFERENCE (UNVERIFIED): the restore of the box does not copy folders that have the names of build output or cache folders. Examples are `build`, `target` and `.cache`.

The evidence for this inference:

1. Folders with these names were lost in two different places (`ucp-demo/build` and `ucp-schema/target`).
2. Large files that are not in such folders survived (the Caddy archive). Thus the cause is not the file size.
3. `.git` folders survived. Thus the cause is not the `.git` name.

I found no document or log that gives the exclusion list. `/tmp/exec-daemon.log` and `/tmp/box-doctor.log` do not show it. Thus the exact list is UNVERIFIED.

## Decision

1. The repository is now at `<repository folder>`. No folder of the repository has a name from the list above.
2. The `ucp-schema` binary goes to `<tools folder>/bin/`, not to a `target/` folder. The Cargo build uses `CARGO_TARGET_DIR=<tools folder>/ucp-schema-cargo-out`.
3. Runtime data stays in `.run/` (not in Git). The run scripts make it again. We do not keep durable data in `.run/`.
4. Bundles are the durable copy:
   - After each commit, `tools/bundle.sh <label>` writes `git bundle create --all` to `<backup folder>/`, with a `.sha256` file. The names have a timestamp. We keep all bundles.
   - At a minimum of each 30 minutes of work, we commit the work on a `wip/` branch and make a bundle.
   - The script does `git bundle verify` and `sha256sum -c` on each bundle.
5. Git remote: `origin` = `https://github.com/mmccalla/ucp-checkout-demo.git` (private, default branch `main`, MIT licence).
   - The box has no Git credential for GitHub (`git ls-remote` stopped with `could not read Username`).
   - I read the initial commit with the read-only GitHub connector: commit `b2e23113a911a46f08476dd105ae5690956ebc89`, tree `3f57d7991e2ce1ae8604a927ca3ab3a52695cb49`, files `.gitignore`, `LICENSE`, `README.md`.
   - I made the same commit object locally from the API data (files, author, committer, `gpgsig`, message). Its hash is `b2e23113a911a46f08476dd105ae5690956ebc89`. Thus `refs/remotes/origin/main` points to the real remote commit.
   - All new history starts on top of `origin/main`. We do not change the initial commit.
   - We do not push until the parent agent tells us that a push works.
   - Update 2026-10-24 23:02 BST: push works. We push to `main` after each commit (normal push only). We never force-push `main`. We do not open a pull request. If a push fails, we stop and report.
   - The commit identity is `Mark McCalla <148059550+mmccalla@users.noreply.github.com>`. Before the first push, we rewrote our two local commits to this identity. Old and new SHAs: `1e965a8fdba5` -> `0a534ff3f1ab`, `48e64dc6f60b` -> `f506b378804b`. The parent of `0a534ff` is the initial commit `b2e2311`.
   - The token for the push is in an environment variable. A credential helper reads it. The token is not in the repository, the remote URL, the logs or the evidence.
6. The upstream `.gitignore` (GitHub Python template) ignores `build/`, `lib/`, `target/`, `*.log`, `*.spec` and `*.manifest`. Thus the repository uses `libs/`, and evidence logs stay outside the repository in `<evidence folder>/`.

## Results

- The old commit SHAs are not in this repository. The evidence README for each slice gives the old SHA and the new SHA.
- If the box starts again, use the newest bundle: `git clone <bundle> repo`.
