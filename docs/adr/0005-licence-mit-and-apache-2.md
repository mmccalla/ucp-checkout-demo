# ADR 0005: MIT licence for the repository, Apache-2.0 for the copied upstream code

- Status: Accepted (decision by Mark, given through the parent agent on 2026-10-24, 22:49 BST).
- Date: 2026-10-24.

## Context

1. Mark made the repository `mmccalla/ucp-checkout-demo` with the MIT licence (`LICENSE`). On 2026-11-03 Mark decided that the holder name is "Mark McCalla" and that the public repository is `mmccalla/ucp-checkout-demo`..
2. The demo copies upstream code and data that use the Apache License, Version 2.0:
   - `rest/python/server` from `Universal-Commerce-Protocol/samples` at commit `e7c9c124864108cbb35e5102beeac9cbef80a154` (`LICENSE` in that repository is Apache-2.0, and each source file has the Apache-2.0 header).
   - The UCP schemas from `https://ucp.dev/2026-04-08/schemas/` and `Universal-Commerce-Protocol/ucp` at commit `9c9d6fce39ffa8bf7cb66309c378b79fb75b5382` (Apache-2.0).
   - `ucp-sdk` 0.4.6 and `ucp-schema` 1.4.1 are dependencies or tools. We do not copy their source.
3. `02-design.md` section 17.2 and engineering OQ-2 tell us to copy only `rest/python/server`, and to add a `NOTICE` file and a provenance file.

## Decision

1. The MIT licence in `LICENSE` applies to the code that we write.
2. The copied upstream files keep the Apache-2.0 licence. We do not remove or change their licence headers.
3. `NOTICE` names each copied upstream part, its licence and its source commit.
4. `UPSTREAM.md` gives the provenance of each copied file and each change (patch) that we made. Apache-2.0 section 4 (b) requires a notice in each changed file. Each patched file gets a comment that tells that we changed it.
5. A copy of the Apache-2.0 text is in `LICENSES/Apache-2.0.txt`.

## Sources

- Apache License 2.0, section 4: https://www.apache.org/licenses/LICENSE-2.0
- Samples licence at the pinned commit: https://github.com/Universal-Commerce-Protocol/samples/blob/e7c9c124864108cbb35e5102beeac9cbef80a154/LICENSE
- UCP licence at the pinned commit: https://github.com/Universal-Commerce-Protocol/ucp/blob/9c9d6fce39ffa8bf7cb66309c378b79fb75b5382/LICENSE

UNVERIFIED: this ADR is not legal advice. A person must do a check of the licence mix before a public release.
