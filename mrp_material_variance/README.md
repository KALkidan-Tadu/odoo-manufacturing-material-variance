# Manufacturing Material Variance Tracker

**Technical name:** `mrp_material_variance`  
**Supported Odoo version:** 18.0

## What it does

This addon compares **planned** raw material consumption with **actual** consumption on manufacturing orders (MOs). It calculates quantity and percentage variances, classifies each component against a company-level tolerance, and helps manufacturing managers spot significant over- or under-consumption.

It extends standard Odoo Manufacturing (`mrp`) and Inventory (`stock`) data. It does **not** replace manufacturing orders, bills of materials, or stock moves.

## Business problem

Planners expect components to be consumed according to the bill of materials and the MO quantity. On the shop floor, actual usage often differs. Without a clear variance view, overconsumption (waste, scrap, wrong picks) and underconsumption (incomplete reporting, missing issues) stay hidden until costing or inventory counts reveal them.

## Dependencies

- `mrp` (which pulls in `stock`, `product`, etc.)

## Installation

1. Place the `mrp_material_variance` directory on your Odoo 18 addons path.
2. Update the apps list.
3. Install **Manufacturing Material Variance Tracker**.

Example (development):

```bash
# Ensure the module is on the addons path, then:
./odoo-bin -c odoo18.conf -d YOUR_DATABASE -i mrp_material_variance --stop-after-init
```

## Configure tolerance

1. Open **Manufacturing → Configuration → Settings** (Manufacturing Administrator).
2. Under **Material Variance**, set **Material Consumption Tolerance** (default **5%**).
3. The value is **company-specific** and cannot be negative.

Only Manufacturing Administrators may change this setting.

## Access material variance analysis

- **From an MO:** open a confirmed/in-progress/done manufacturing order and click the **Material Variance** smart button.
- **From reporting menus:** **Manufacturing → Reporting → Material Variance → Material Variances** (refreshes analysis, then opens the list).
- **Summary:** **Manufacturing → Reporting → Material Variance → Variance Summary**.

Manufacturing Users can view analysis for MOs they are allowed to access. They cannot change the global tolerance.

## How quantities are calculated

### Planned quantity

Taken from the MO component moves (`mrp.production.move_raw_ids` → `stock.move.product_uom_qty`, labeled **To Consume** in the UI). That demand already reflects the MO quantity and BoM (or manually adjusted component lines). Quantities are converted to the component’s default unit of measure before comparison.

Cancelled raw moves still contribute to planned quantity when Odoo retains their demand (typical when a component was planned but not consumed).

### Actual quantity

Taken only from consumption that has been **picked** or **done**, using `stock.move._get_picked_quantity()`. Reserved but not picked stock is ignored. Cancelled moves are excluded from actuals.

### Variance formulas

- `Variance = Actual − Planned`
- `Variance % = (Variance / Planned) × 100`
- If planned is **0** and actual is **0** → variance % = 0, classification = Within Tolerance
- If planned is **0** and actual &gt; 0 → treated as Overconsumption (no division by zero)

### Classification (tolerance T, default 5)

| Condition | Classification |
| --- | --- |
| \|Variance %\| ≤ T | Within Tolerance |
| Variance % &gt; T | Overconsumption |
| Variance % &lt; −T | Underconsumption |

Boundaries are inclusive (exactly ±T is within tolerance).

### Eligible MO states

`confirmed`, `progress`, `to_close`, `done`

Draft and cancelled MOs are not analyzed. Lines for MOs that are not `done` are marked **Provisional**.

## Worked example

BoM for 1 finished product requires **200** wooden boards. MO quantity = 1.

| | Boards |
| --- | ---: |
| Planned | 200 |
| Actual | 220 |
| Variance | +20 |
| Variance % | +10% |
| Tolerance | 5% |
| Classification | Overconsumption |

## Architecture notes

- Model `mrp.material.variance`: one stored analysis line per MO / component, linked to the underlying raw `stock.move` records.
- Calculation fields are computed (and stored for search/group) from live move data; lines are synchronized when opening the analysis (no duplicate copies of MOs/BoMs).
- Company field `material_variance_tolerance` holds the default tolerance (designed so product-specific tolerances can be added later).

## Known limitations

- Product- or component-specific tolerances are not implemented yet (company default only).
- Analysis lines are refreshed when opening the variance views/actions, not via a continuous realtime bus.
- Kit/phantom BoM explosion edge cases follow whatever component moves MRP created; this module does not re-explode BoMs.
- Scrap moves (`scrapped`) are excluded from aggregation.

## Running automated tests

```bash
./odoo-bin -c odoo18.conf -d YOUR_TEST_DB \
  -i mrp_material_variance \
  --test-enable \
  --stop-after-init \
  --log-level=test \
  2>&1 | tee /tmp/mrp_material_variance_tests.log
```

Or tag-filter to this module’s tests after install:

```bash
./odoo-bin -c odoo18.conf -d YOUR_TEST_DB \
  --test-enable \
  --stop-after-init \
  --test-tags=/mrp_material_variance
```

## Security

| Group | Variance analysis | Tolerance setting |
| --- | --- | --- |
| Manufacturing User | Read (company-restricted) | No |
| Manufacturing Administrator | Full | Yes |
