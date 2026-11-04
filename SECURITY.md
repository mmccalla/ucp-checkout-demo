<!--
Draft for the root of the repository (GitHub shows it in the "Security" tab).
Docs: https://docs.github.com/en/code-security/getting-started/adding-a-security-policy-to-your-repository
Private vulnerability reporting: https://docs.github.com/en/code-security/security-advisories/working-with-repository-security-advisories/configuring-private-vulnerability-reporting-for-a-repository
Mark must turn it on in the repository settings after the repository is public (plan row 8). This draft changes no setting.
Decision of Mark (2026-11-03): reports go only through GitHub private vulnerability reporting. No e-mail address.
Remove this comment block before publication.
-->

# Security policy

This project is a demo of the Universal Commerce Protocol (UCP). It is not a product. Do not use it to take real payments.

## Versions with support

| Version | Support |
|---|---|
| The default branch (`main`) | Yes |
| Other branches and old commits | No |

## How to report a problem with the safety of the code

Do not open a public issue for a security problem. Use the private report form of GitHub. This is the only way to report.

1. Go to the "Security" tab of this repository.
2. Select "Advisories".
3. Select "Report a vulnerability".

How the form works: https://docs.github.com/en/code-security/security-advisories/working-with-repository-security-advisories/configuring-private-vulnerability-reporting-for-a-repository

Write these items in your report:

- The file and the line, or the address of the page.
- The steps that show the problem.
- The effect that you see.
- The commit that you tested (`git rev-parse HEAD`).

## What to expect

The owner of this project works alone. The owner gives no answer time.

The owner reads each report, tells you the result, and writes a fix if the report is correct. The owner can ask you for more data. Please do not tell other persons about the problem until the owner publishes the fix.

## What is in scope

- The code in this repository (the Platform, the Business, the PSP mock, the libraries and the tools).
- The files for deployment in `deploy/`.
- The workflow in `.github/workflows/`.

## What is not in scope

- The demo uses test keys, the dummy token and test data on purpose. These are not secrets.
- The local certificate authority of Caddy (it is for `localhost` only).
- Faults in Google Pay, in the UCP schemas, or in other third-party code. Report these faults to their owners. See `NOTICE` for the list.
- Attacks that are possible only on a computer with changed local files.

## A secret that you find in the history

If you find a real secret value in this repository, report it with the private form. Do not copy the value into the report. Write the file and the commit only.
