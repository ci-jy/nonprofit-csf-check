# csfcheck: a NIST CSF 2.0 self-assessment for small non-profits

csfcheck is a cybersecurity self-assessment for small charities, food banks and student societies, scored against NIST CSF 2.0. Formal risk assessments assume a security team and money for consultants, so small organisations mostly never do one ([this study of NGOs](https://www.emerald.com/insight/content/doi/10.1108/TG-08-2024-0201/full/html) found the same). I wanted something an office manager could finish alone in a browser, ending in a heat map, a ranked action plan, a Word report for the board and an Excel workbook.

It doesn't scan anything and it isn't a certification. It only records what the organisation says it does.

## Running it

You need Python 3.11+ and PostgreSQL. PostgreSQL has to be installed but not running, because the tests and `serve --temp-db` start their own throwaway cluster and delete it afterwards.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

python3 -m pytest
python3 -m csfcheck serve --temp-db --port 23180
```

Then open http://127.0.0.1:23180/. You give the organisation's name and ten yes/no facts about it (premises, online donations, client records and so on), then answer the questions one CSF function at a time. There are no accounts. You get a resume code once, and that's how you carry on from another computer or come back later for a retake.

The same scoring runs from the command line on an answers file. Here is the made-up food bank sample a year after its first assessment, compared with the first one:

```
$ python3 -m csfcheck export samples/retakes/food_bank.json --previous samples/food_bank.json -o out/food_bank_v2.xlsx --top 3
since food_bank.json: 18 subcategories improved, 3 regressed, 4 of 85 actions completed, target reached 27% -> 34%
Riverside Community Food Bank: asked 91 of 100 questions (9.0% skipped), 104 subcategories assessed, 82 actions
   1. PR.AA-02  Critical low    Verify a person's claimed identity at enrollment time using government-issued id
   2. PR.AT-02  High     free   Identify the specialized roles within the organization that require additional c
   3. ID.AM-03  High     free   Maintain baselines of communication and data flows within the organization's wir
wrote out/food_bank_v2.xlsx
```

With Docker, `docker compose up --build --detach --wait` starts PostgreSQL and the app and `docker compose down -v` removes them. If you only want to look, [docs/samples/](docs/samples/) has a finished workbook and Word report.

More detail: [commands](docs/cli.md), [web pages and report](docs/web.md), [JSON API](docs/api.md), [Docker](docs/docker.md), [scoring](docs/scoring.md), [question bank](docs/question-bank.md), [workbook](docs/workbook.md), [retakes](docs/retakes.md), [data sources](docs/data-sources.md).

## How it works

The CSF core is NIST's own JSON export from their reference tool, stored with its SHA-256, and the loader refuses a file that doesn't match. One surprise was that the export still carries the withdrawn CSF 1.1 subcategories. They have to be filtered out to get the 106 that are actually in CSF 2.0.

The 100 questions live in one YAML file, each mapped to one or more subcategories and answered on a 0 to 3 scale. The profile flags decide which questions apply, so a student club with no premises is never asked about door codes. Follow-ups only open when the parent answer is good enough. If you have no backups, you aren't asked whether you test them.

Making sure nothing fell through the gaps was the fiddly part. At startup the bank is checked against all 1,024 combinations of flags, and every subcategory has to be either asked about or excluded with a reason. A typo in a flag name stops the app before it serves anything.

Targets come from NIST's Small Business Quick-Start Guide. The gap between current and target drives likelihood, and actions are ranked by how much risk they remove per unit of cost. The rule I cared most about is that improving an answer can never raise a risk score, and a Hypothesis property test checks it.

A retake is a new version with its own profile and answers. One function lines two versions up, and the progress page, the workbook and the report all use it.

## Known issues and next steps

- The inherent likelihood and impact numbers are my own rough judgements for a small charity, not data. They sit in one file so they're easy to argue with.
- The action plan is long, one action per gap. Grouping related actions into a single task would make it much easier to read.
- When the profile changes, new questions get averaged into subcategories that were already scored. The food bank started letting someone work from home, two home-device questions came in low, and PR.DS-01 shows as a regression even though nothing in the office got worse.
- The resume code is the only access control and it opens every version. Lose it and you lose the history.

Project period: 2026-09-08 to 2026-10-07.
