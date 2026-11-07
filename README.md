# Odoo POS Customizations (Odoo 17)

![Odoo](https://img.shields.io/badge/Odoo-17.0-purple) ![Modules](https://img.shields.io/badge/Custom%20Modules-2-blue) ![License](https://img.shields.io/badge/License-LGPL--3-green)

Two advanced **POS extensions** built as **modifications & feature additions** on the existing Odoo 17 POS (base: Softhealer `sh_pos_all_in_one_retail` retail suite):

1. **Pos SC/PWD HMRC** — a statutory **Senior Citizen / Person With Disability (SC/PWD) discount engine** with VAT-net discount calculation, session login, audit trail, e-journal and a stack of POS reports.
2. **Pos Voice Agent** — a voice-driven POS assistant: **wake-word detection** plus **fuzzy product search** (rapidfuzz) to add products by speaking.

```
odoo-pos-customizations/
├── pos_sc_pwd_hmrc/        # SC/PWD discount engine + audit + POS reporting suite
└── pos_agent/              # Voice agent (wake word + fuzzy product search)
```

## Pos SC/PWD HMRC

> For SC/PWD transactions, **the discount is applied on the net of VAT price** — the system first removes VAT from the selling price, then applies the standard discount rate on that amount.

Key capabilities:

- Dedicated **discount engine** (`discount_engine.js`, `discount_calculator.js`, `order_discount.js`, `orderline_discount.js`) injected into `point_of_sale._assets_pos`.
- Group-driven discount entitlements (security `res_groups.xml`), fiscal positions and payment-method overrides.
- **Session login popup & POS close patches**, numpad and product-screen patches, custom **receipt template** for discounted orders.
- Built-in **compliance/audit tooling**: audit log views, HTTP session/request views, audit-trail wizard, price-change report, e-journal wizard, annex report, e-sales report, product/employee add-remove reports.

## Pos Voice Agent

- **Wake word listener** (`wake_word.js`) loaded into POS assets — hands-free trigger.
- `/voice/search_product` JSON controller matches spoken queries against POS products using **rapidfuzz** strategies in cascade (`token_sort_ratio → partial_ratio → token_set_ratio`).
- Adds the best-matching product back into the POS session.

## Dependencies

- `pos_sc_pwd_hmrc`: `sh_pos_all_in_one_retail` (3rd-party POS suite), `account`
- `pos_agent`: `point_of_sale` (+ `rapidfuzz` Python package on the Odoo server)

## License

LGPL-3 (as declared in module manifests).
