# Workbook

`python3 -m csfcheck export <answers.json> -o <file.xlsx>` and `GET /assessments/{id}/workbook` both write the same workbook.

CLI options for `export`: `--top N` sets how many actions are printed (default 5). `--allow-incomplete` makes it exit 0 even when some asked questions are unanswered.

## Sheets

- Summary: organisation, question counts and totals.
- Profile: one row per CSF 2.0 subcategory (106 rows). Columns: Function, Category, Subcategory, Outcome, Status, Current (0-3), Target (0-3), Gap, Target basis, Questions, Not applicable because.
- Gaps: assessed subcategories with a gap, highest risk first. Columns: Subcategory, Function, Outcome, Current, Target, Gap, Likelihood (1-5), Impact (1-5), Risk (1-25), Rating, Unanswered questions.
- Action Plan: one row per gap, in rank order. Columns: Rank, Horizon, Subcategory, What to do (CSF implementation example), Also consider, Quick-Start Guide action, Cost band, Risk now, Risk reduced, Reduction per cost unit, Example IDs, Owner, Status. Status has a dropdown.
- Evidence Log: one row per asked question. Columns: Question, Section, Question text, Answer, Score (0-3), Subcategories, Evidence offered, Auditor: evidence seen?, Auditor notes. The last two are left for the auditor.
