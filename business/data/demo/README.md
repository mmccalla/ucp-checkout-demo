# Demo data (S2)

These CSV files use the format of the samples `test_data/flower_shop` files at commit `e7c9c12`.
The sample script `import_csv.py` reads them.

| File | Content |
|---|---|
| `products.csv` | `demo_tshirt` (Demo T-shirt, 2000 = £20.00) and `demo_mug` (1200 = £12.00). Amounts are integers in minor units (GBP pence). |
| `inventory.csv` | `demo_tshirt` has stock. `demo_mug` has 0, for the out-of-stock test (AC-14). |
| `shipping_rates.csv` | One delivery option for GB: `gb-standard`, 300 = £3.00 (02-design: "Delivery £3.00"). There is no `default` rate, so an address outside GB gets `address_undeliverable` (AC-14). |
| Other files | Header row only. The demo has no customers, addresses, discounts, promotions or stored instruments. |
