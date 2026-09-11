# Scoring and risk model

The scoring lives in `src/csfcheck/engine.py`. The inherent numbers it uses are in `src/csfcheck/data/risk_model.yaml`, and the targets come from `src/csfcheck/data/quickstart.yaml`.

## Per subcategory

| Quantity | How it's computed |
|---|---|
| current | mean answer score (0-3) of the applicable questions mapped to the subcategory. Unanswered questions and skipped follow-ups count as 0 |
| target | Quick-Start tier, 1 to 3 (see below) |
| gap | `max(0, target - current)` |
| likelihood | `1 + (inherent likelihood - 1) * gap / target`, so a closed gap leaves 1 |
| impact | the category's inherent impact, raised by profile flags |
| risk | `likelihood * impact` (1-25) |

Ratings: up to 4 is Low, up to 9 Medium, up to 15 High, up to 25 Critical.

## Targets

`quickstart.yaml` lists the 41 "Actions to Consider" from the NIST CSF 2.0 Small Business Quick-Start Guide, with the CSF references printed next to each one.

- 3: the guide names the subcategory directly (38 subcategories)
- 2: the guide names its category (17)
- 1: everything else, meaning at least done informally (51)

`python -m csfcheck check` prints these counts.

## Inherent likelihood, impact and cost

Each of the 22 CSF categories has an inherent likelihood and impact (1-5) and a cost band. A few subcategories override their category's cost band, for example MFA and password managers (`PR.AA-03`) are `low`, and cyber insurance (`GV.RM-04`) is `medium`.

Cost bands and their weights:

- free (time only): 1
- low (under about $500 a year): 2
- medium (about $500 to $5,000): 3
- high (over about $5,000 or a managed service): 5

Profile flags add 1 to some categories' likelihood or impact, capped at 5:

- `remote_staff`: likelihood of PR.AA, PR.IR, PR.DS
- `takes_payments`: likelihood of PR.AA, DE.CM; impact of PR.DS, RS.CO
- `holds_donor_data`: impact of PR.DS, ID.AM, RS.CO
- `holds_client_data`: impact of PR.DS, PR.AA, GV.OC
- `has_servers`: likelihood of PR.PS; impact of PR.IR, RC.RP
- `uses_it_provider`: likelihood of GV.SC
- `develops_software`: likelihood of ID.RA

## Action plan

Every assessed subcategory with a gap above 0 gets one action. Its wording is the subcategory's first NIST implementation example, and the next two are listed under "Also consider".

- risk reduced = current risk minus the closed-gap risk (`1 * impact`)
- priority = risk reduced / cost-band weight

Actions are sorted by priority, then by risk, then by CSF ID so the order is stable. Ranks 1-5 are "Now", 6-15 "Next" and the rest "Later".

Improving any single answer never raises a subcategory's risk or the total. `tests/test_properties.py` checks this with Hypothesis.
