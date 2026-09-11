# Question bank

The bank is `src/csfcheck/data/questions.yaml`. It is loaded and checked at startup, and the app refuses to start if the check fails.

## Profile flags

| Flag | Meaning |
|---|---|
| `has_office` | Premises (office, warehouse, studio or hall) where equipment is kept |
| `has_servers` | Own server or NAS rather than only cloud services |
| `uses_cloud_email` | Microsoft 365 or Google Workspace with an admin console |
| `takes_payments` | Card payments, online donations or online bank transfers to suppliers |
| `remote_staff` | Staff or volunteers work from home or on their own devices |
| `holds_donor_data` | Records of donors or members |

The other four are `holds_client_data` (sensitive information about the people you serve), `has_employees` (paid staff, not only volunteers), `uses_it_provider` (an outside IT company or freelancer) and `develops_software` (own website code, app or plugins).

## Answer scales

`maturity`:

- `no`: No, or not sure (0)
- `informal`: Sometimes, depends on one person remembering (1)
- `mostly`: Mostly, but not written down or not checked (2)
- `yes`: Yes, written down and checked at least once a year (3)

`yesno`: `no` (0) or `yes` (3).

## Question fields

- `id`, `section`, `text`
- `maps`: the CSF 2.0 subcategory IDs the question scores
- `when`: a boolean expression over profile flags, e.g. `has_office or has_servers`. If it is false, the question is never asked and doesn't count towards any score.
- `requires`: a parent question and minimum score. If the parent scores lower, the follow-up is skipped and scores 0.

## Exclusions

An exclusion lists subcategories, a `when` condition and a `reason`. For example, `PR.PS-06` and `ID.RA-08` are excluded when `not develops_software`. The reason is written to the Profile sheet of the workbook.

## Coverage check

The bank is checked against all 1,024 combinations of the ten flags. In every combination, each subcategory must be either reachable by a question or excluded by a rule, never both and never neither. Unknown flag names, IDs that aren't in CSF 2.0 (such as withdrawn 1.1 subcategories) and coverage gaps are all errors.

## Answers files

The samples in `samples/` show the format the CLI reads: an `organisation` object with `name`, `description` and `profile`, and an `answers` object mapping question IDs to answer values.
