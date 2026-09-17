# csfcheck: a NIST CSF 2.0 self-assessment for small non-profits

csfcheck is a cybersecurity self-assessment for small charities, food banks and student societies, scored against NIST CSF 2.0. Formal risk assessments assume a security team, written processes and money for consultants, so small organisations mostly never do one ([this study of NGOs](https://www.emerald.com/insight/content/doi/10.1108/TG-08-2024-0201/full/html) found the same). I wanted something an office manager could finish alone in a browser, ending in a heat map of where they stand, a ranked action plan, a Word report for the board and an Excel workbook an auditor can work from.

It doesn't scan anything and it isn't a certification. It records what the organisation says it does and the evidence it offers.

## Running it

You need Python 3.11+ and PostgreSQL. PostgreSQL only has to be installed, not running, because the tests and `serve --temp-db` start their own throwaway cluster and delete it again when they stop.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

python3 -m pytest
python3 -m csfcheck serve --temp-db --port 23180
```

Then open http://127.0.0.1:23180/. The start page asks for the organisation's name and ten yes/no facts about it (do you have premises, take online donations, keep client records...). After that the questions come one CSF function at a time, each with a line of plain-language help and an optional box for evidence. There are no accounts. You get a resume code once, so you can carry on from another computer.

![A Govern question with its help text, the section steps and the progress bar](docs/web-questions.png)

When you finish you land on the heat map, which links on to the action plan, the Word report and the workbook.

![Heat map page for the food bank sample](docs/web-heatmap.png)

The same scoring runs from the command line on an answers file. `export` writes the workbook and prints the top actions:

```
$ python3 -m csfcheck export samples/food_bank.json -o out/food_bank.xlsx
Riverside Community Food Bank: asked 86 of 100 questions (14.0% skipped), 104 subcategories assessed, 85 actions
   1. RS.CO-02  High     free   Follow the organization's breach notification procedures after discovering a dat
   2. RS.CO-03  High     free   Securely share information consistent with response plans and information sharin
   3. PR.AT-01  High     free   Provide basic cybersecurity awareness and training to employees, contractors, pa
   4. PR.AT-02  High     free   Identify the specialized roles within the organization that require additional c
   5. ID.AM-03  High     free   Maintain baselines of communication and data flows within the organization's wir
wrote out/food_bank.xlsx
```

`report` writes the Word report from the same file, `stats` shows what each sample skipped and `check` verifies the CSF data and the question bank.

Commands and flags: [docs/cli.md](docs/cli.md)
Web pages, the heat map and the Word report: [docs/web.md](docs/web.md)
JSON API with an example curl session: [docs/api.md](docs/api.md)

## How it works

The CSF core is NIST's own JSON export from their Cybersecurity and Privacy Reference Tool, stored with its SHA-256, and the loader refuses a file that doesn't match. One surprise was that the export still carries the withdrawn CSF 1.1 subcategories. Those have to be filtered out to get the 106 that are actually in CSF 2.0.

The 100 questions live in one YAML file, each mapped to one or more subcategories and answered on a 0 to 3 scale. The profile flags decide which questions apply, so a student club with no premises is never asked about door codes. Follow-ups only open when the parent question scored well enough. If you have no backups, you aren't asked whether you test them.

The fiddly part was making sure nothing falls through the gaps. At startup the bank is checked against all 1,024 combinations of flags, and every subcategory has to be either asked about or excluded with a reason, never both and never neither. A typo in a flag name or a mapping to an old 1.1 ID stops the app before it serves anything.

Targets come from NIST's Small Business Quick-Start Guide. The gap between current and target drives likelihood, impact goes up with things like holding donor data, and actions are ranked by how much risk they remove per unit of cost. The inherent numbers are my own coarse judgements for a small charity, kept in one file so they're easy to argue with. The rule I cared most about is that improving an answer can never raise a risk score. A Hypothesis property test checks it.

The three samples are made-up organisations. Rolled up by function, this is the share of their target they reach:

| Share of target reached | Govern | Identify | Protect | Detect | Respond | Recover | Overall |
|---|---|---|---|---|---|---|---|
| Food bank | 33% | 19% | 46% | 30% | 10% | 11% | 27% |
| Student club | 10% | 11% | 38% | 21% | 8% | 0% | 15% |
| Arts charity | 71% | 55% | 73% | 67% | 52% | 53% | 63% |

All three do best on Protect and worst on Respond or Recover. People buy antivirus and turn on passwords, but nobody has written down what to do on the day the donor database is encrypted. Only 13% of the bank gets skipped on average, which is less than I expected. Most of the CSF is governance and incident handling, and that applies however small you are.

Scoring and risk model: [docs/scoring.md](docs/scoring.md)
Question bank format and profile flags: [docs/question-bank.md](docs/question-bank.md)
Workbook sheets and columns: [docs/workbook.md](docs/workbook.md)
Data sources and licences: [docs/data-sources.md](docs/data-sources.md)

## Known issues and next steps

- The likelihood and impact numbers are judgement, not data. Two people could set them differently, although the ranking depends far more on gap size and cost band.
- The action plan is long, between 53 and 90 actions for the samples, one per gap. Grouping related ones (all the incident-response actions, say) into one task would make it much easier to read.
- Answers are averaged per subcategory, so a strong answer can hide a weak one. Using the minimum would be stricter, but harsher on small organisations.
- The Word report has no heat map image, only a shaded category table, because python-docx can't embed SVG. Next I'd like to compare two assessments of the same organisation, so a charity can see a year's progress on the heat map.

Project period: 2026-09-08 to 2026-09-17.
