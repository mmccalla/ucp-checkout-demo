# Conformance input (G5)

- `conformance_input.json` is `test_data/flower_shop/conformance_input.json` at the pinned suite
  commit (see `../PIN`) with one change: `required_capabilities` lists only the capabilities that
  the Business declares (`checkout`, `order`, `fulfillment`). The demo has no discount and no
  buyer consent (spec section 1.3). The README of the suite says that this file is merchant input.
- `test_fixtures.json` is the file of the suite without a change.
- `shopping-agent-ci-profile.json` is `shopping-agent-test.json` at the same commit with two added
  keys: `"services": {}` and `"payment_handlers": {}`.
- The Business data comes from `test_data/flower_shop/*.csv` of the suite (the gate imports it).
