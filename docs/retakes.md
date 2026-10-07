# Retakes and the food bank comparison

Each retake is a new version of the assessment, with its own profile and answers, linked to the one before and opened by the same resume code. The earlier version is never changed. By default the new version starts with the old answers and evidence copied in, and questions that a changed profile adds are left blank.

`src/csfcheck/compare.py` lines two scored versions up subcategory by subcategory and reads the old action plan against the new scores. Each old action ends up as one of:

- completed: the gap is closed
- progressed: the gap is smaller
- still open
- no longer applicable: the profile change took the subcategory out of scope

Subcategories can also become newly applicable, and an action can be new when a subcategory went backwards. The progress page, the workbook's Progress sheet, the report's "Progress since ..." section and the API's `/compare` all come from this one function. A Hypothesis test in `tests/test_compare.py` checks that raising any set of answers never shows a regression or a new action.

## The food bank sample

`samples/food_bank.json` is a fictional food bank. Share of its target reached per function on the first assessment (pinned by `tests/test_heatmap.py`):

| Govern | Identify | Protect | Detect | Respond | Recover |
|---|---|---|---|---|---|
| 33% | 19% | 46% | 30% | 10% | 11% |

`samples/retakes/food_bank.json` is the same food bank a year on. It enforces 2-step verification for everyone, has a two-page incident plan and has tested one restore. The coordinator who looked after IT has left, and one coordinator now works from home. Against the first assessment (pinned by `tests/test_compare.py`):

| | First | Second |
|---|---|---|
| Share of target reached | 27% | 34% |
| Subcategories at target | 19 | 22 |
| Respond, share of target | 10% | 32% |
| Actions in the plan | 85 | 82 |

18 subcategories improved and 3 went backwards (GV.RR-02, PR.AA-05, PR.DS-01). 4 old actions are completed (RC.RP-04, RS.MA-02, RS.MA-04, GV.RM-06) and 14 progressed. GV.RR-02 is back in the plan because nobody owns IT any more.

PR.DS-01 is the misleading one. Ticking "staff work from home" adds two questions about home devices that map to it, they come in low, and data-at-rest drops from 1.00 to 0.75 without anything getting worse in the office.

## Limitations

- A retake compares with the version it was retaken from. Comparing version 3 with version 1 works through the API (`?with=`), but the pages and the workbook only show the last step.
- A profile change can look like a regression, as with PR.DS-01 above. Telling "you got worse" apart from "more of your organisation is now being asked about" would need another column.
- The Word report's progress section is a table, not a before-and-after heat map, because python-docx can't embed SVG.
