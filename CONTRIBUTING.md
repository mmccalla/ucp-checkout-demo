<!--
Draft for the root of the repository. GitHub links this file in the "New issue" and "New pull request" pages.
Docs: https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/setting-guidelines-for-repository-contributors
Community health files: https://docs.github.com/en/communities/setting-up-your-project-for-healthy-contributions/creating-a-default-community-health-file
Remove this comment block before publication.
-->

# How to contribute

Thank you for your interest. This project is a demo of the Universal Commerce Protocol (UCP). One person owns it.
The owner works alone and answers when he can. The owner gives no answer time.

## Before you start

- Read `README.md` and make the demo run on your computer.
- Read `CODE_OF_CONDUCT.md`. All contributors must follow it.
- For a security problem, read `SECURITY.md`. Do not open a public issue.
- For a big change, open an issue first. Wait for an answer before you write code.

## Report a bug

1. Search the open and closed issues. Find out if another person reported the bug.
2. Open a new issue. Use the template "Bug report".
3. Write the steps, the result that you want, and the result that you get.
4. Write the commit (`git rev-parse HEAD`) and your operating system.
5. Do not put secret data in the issue. A log can contain a token. Read the log before you copy it.

## Suggest a feature

Open an issue with the template "Feature request". Write the problem first. Then write your idea. The project keeps the scope small. The owner can say no.

## Send a change (pull request)

1. Fork the repository and make a branch from the default branch. The branch is `main`.
2. Install the tools. Use the steps in `README.md` (`uv sync --locked`, Caddy, `ucp-schema`).
3. Make your change. Keep it small. One pull request does one thing.
4. Add or change tests for your change. The tests are in `tests/`.
5. Run the unit tests and the gates. Make sure that they pass. The steps are in `README.md`, sections "Tests" and "Gates".
6. Open the pull request. Use the template. Link the issue.

### What the checks do

- The workflow `.github/workflows/ci.yaml` has one job, `gates`. It runs the gates and the tests.
- The first workflow run of a new contributor needs approval from the owner. This is a GitHub setting for forks. See https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-workflow-runs/approving-workflow-runs-from-public-forks
- The pull request can merge only when the job `gates` passes. This rule is active only after the owner turns on the ruleset.
- The owner merges with "squash" or "rebase". The history of the default branch stays linear.

### Rules for the code

- Do not add a secret, a key, or a personal path to a file. Use the environment variables and the test values in the repository.
- Pin each new tool or action to an exact version or to a full commit SHA, as in `.github/workflows/ci.yaml`.
- Do not change a copy of a third-party file in `contracts/` or `libs/`. These files are copies without change. See `NOTICE`.
- Do not add a custom Google Pay button. The Google Pay brand guidelines require the official button. See https://developers.google.com/pay/api/web/guides/brand-guidelines
- Write the text in `README.md` and in `docs/` in short, plain sentences.

## Licence of your contribution

When you send a change, you agree that your change uses the same licence as the file that you change. The code of this project uses the MIT licence (`LICENSE`). Some files keep other licences (`NOTICE`).
The project has no signed-off line (DCO) and no contributor agreement.

## Questions

Open an issue with the label "question". GitHub Discussions are off.
