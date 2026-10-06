# Command line

Everything runs as `python3 -m csfcheck <command>`.

## export

```bash
python3 -m csfcheck export samples/food_bank.json -o out/food_bank.xlsx
```

Scores an answers file, writes the Excel workbook and prints a one-line summary plus the top actions.

- `-o`, `--output`: workbook path (required)
- `--top N`: how many actions to print (default 5)
- `--previous FILE`: an earlier answers file for the same organisation. The workbook's Progress sheet then compares the two instead of showing a baseline
- `--allow-incomplete`: exit 0 even if some applicable questions are unanswered (otherwise exits 1)

An answers file that doesn't fit the bank (unknown question, invalid score) exits 2. The same goes for the `--previous` file.

Comparing the food bank's second assessment with its first:

```
$ python3 -m csfcheck export samples/retakes/food_bank.json --previous samples/food_bank.json -o out/food_bank_v2.xlsx --top 3
since food_bank.json: 18 subcategories improved, 3 regressed, 4 of 85 actions completed, target reached 27% -> 34%
Riverside Community Food Bank: asked 91 of 100 questions (9.0% skipped), 104 subcategories assessed, 82 actions
   1. PR.AA-02  Critical low    Verify a person's claimed identity at enrollment time using government-issued id
   2. PR.AT-02  High     free   Identify the specialized roles within the organization that require additional c
   3. ID.AM-03  High     free   Maintain baselines of communication and data flows within the organization's wir
wrote out/food_bank_v2.xlsx
```

## report

```bash
python3 -m csfcheck report samples/student_club.json -o out/student_club.docx
```

Writes the Word findings report. Example output:

```
Campus Robotics Society: 11 of 101 subcategories at target, 90 actions, top 10 in the report
wrote out/student_club.docx
```

- `-o`, `--output`: report path (required)
- `--top N`: how many actions go in the report (default 10)
- `--previous FILE`: an earlier answers file; adds a "Progress since ..." section after the executive summary
- `--allow-incomplete`: as for `export`

## stats

```bash
python3 -m csfcheck stats samples/*.json
```

For each answers file: questions asked, questions skipped by the profile, follow-ups skipped, the skipped percentage and how many subcategories were excluded. Ends with the mean skipped percentage.

## check

```bash
python3 -m csfcheck check
```

Verifies the vendored CSF export against its checksum and prints the catalog counts, the question bank size, the number of profiles the coverage check ran over and how many subcategories got each Quick-Start target.

## load-csf

Imports the CSF 2.0 core into a PostgreSQL database.

- `--database-url`: target database (or set `CSFCHECK_DATABASE_URL`)

## Rebuilding the samples in docs/

```bash
python3 scripts/build_doc_samples.py
```

Writes `docs/samples/food_bank_v2.xlsx` and `docs/samples/food_bank_v2.docx` from the two food bank answers files.

## serve

Runs the web questionnaire and the JSON API in one process.

- `--temp-db`: start a throwaway local PostgreSQL, removed again on Ctrl-C or SIGTERM
- `--database-url`: use an existing database instead (or set `CSFCHECK_DATABASE_URL`)
- `--host`: default `127.0.0.1`
- `--port`: default `23180`
