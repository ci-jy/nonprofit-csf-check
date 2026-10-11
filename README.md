# csfcheck: a NIST CSF 2.0 self-assessment for small non-profits

csfcheck walks a small charity, food bank or student society through up to 100 plain-language questions in a browser and turns the answers into a NIST CSF 2.0 heat map, a ranked action plan, a Word report for the board and an Excel workbook. Run it again later and it shows what changed. On the made-up food bank sample, the second assessment moves the share of its target reached from 27% to 34%, and Respond goes from 10% to 32% once it has a two-page incident plan.

Formal risk assessments assume a security team and money for consultants, so small organisations mostly never do one ([this study of NGOs](https://www.emerald.com/insight/content/doi/10.1108/TG-08-2024-0201/full/html) found the same). I wanted something an office manager could finish alone. It doesn't scan anything and it isn't a certification. It only records what the organisation says it does.

## The food bank, a year on

This is the command-line version of that comparison, with the second answers file checked against the first:

```
$ python3 -m csfcheck export samples/retakes/food_bank.json --previous samples/food_bank.json -o out/food_bank_v2.xlsx --top 3
since food_bank.json: 18 subcategories improved, 3 regressed, 4 of 85 actions completed, target reached 27% -> 34%
Riverside Community Food Bank: asked 91 of 100 questions (9.0% skipped), 104 subcategories assessed, 82 actions
   1. PR.AA-02  Critical low    Verify a person's claimed identity at enrollment time using government-issued id
   2. PR.AT-02  High     free   Identify the specialized roles within the organization that require additional c
   3. ID.AM-03  High     free   Maintain baselines of communication and data flows within the organization's wir
wrote out/food_bank_v2.xlsx
```

Between the two runs the food bank turned on 2-step verification for everyone, wrote the incident plan and tested one restore. It also lost the coordinator who looked after IT, so GV.RR-02 went backwards and is back in the plan. Not every regression is that honest, though (see the last section). The web version of the same comparison is the [progress page](docs/web-progress.png), and [docs/samples/](docs/samples/) has the finished workbook and Word report if you only want to look.

## Trying it

You need Python 3.11+ and PostgreSQL. PostgreSQL has to be installed but not running, because the tests and `serve --temp-db` start their own throwaway cluster and delete it afterwards.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

python3 -m pytest
python3 -m csfcheck serve --temp-db --port 23180
```

Then open http://127.0.0.1:23180/. You give the organisation's name and ten yes/no facts about it (premises, online donations, client records and so on), then answer one CSF function at a time. There are no accounts. You get a resume code once, and that's how you carry on from another computer or come back for a retake.

With Docker, `docker compose up --build --detach --wait` starts PostgreSQL and the app, and `docker compose down -v` removes them.

Reference: [commands](docs/cli.md), [web pages and report](docs/web.md), [JSON API](docs/api.md), [Docker](docs/docker.md), [scoring](docs/scoring.md), [question bank](docs/question-bank.md), [workbook](docs/workbook.md), [retakes](docs/retakes.md), [data sources](docs/data-sources.md).

## Under the hood

The CSF core is NIST's own JSON export from their reference tool, stored with its SHA-256, and the loader refuses a file that doesn't match. I didn't expect the export to still carry the withdrawn CSF 1.1 subcategories. They have to be filtered out to get the 106 that are really in CSF 2.0.

The questions sit in one YAML file, each mapped to one or more subcategories and answered on a 0 to 3 scale. The profile flags decide what gets asked, so a student club with no premises never sees a question about door codes. Follow-ups only open when the parent answer is good enough: no backups, no question about testing them.

The fiddly part was making sure nothing fell through the gaps. At startup the bank is checked against all 1,024 combinations of flags, and every subcategory has to be either asked about or excluded with a reason. A typo in a flag name stops the app before it serves a page.

Targets come from NIST's Small Business Quick-Start Guide. The gap between current and target drives likelihood, and actions are ranked by risk removed per unit of cost. The rule I cared about most is that improving an answer can never raise a risk score. A Hypothesis property test checks it, and another checks that raising answers never shows up as a regression in a retake.

## Rough edges

- The inherent likelihood and impact numbers are my own rough judgements for a small charity, not data. They live in one file so they're easy to argue with.
- The action plan is long, one action per gap. Grouping related actions into a single task would make it far easier to read.
- A profile change can look like getting worse. The food bank started letting someone work from home, two home-device questions came in low, and PR.DS-01 shows as a regression even though nothing in the office changed.
- The resume code is the only access control and it opens every version. Lose it and you lose the history.

Project period: 2026-09-08 to 2026-10-13.
