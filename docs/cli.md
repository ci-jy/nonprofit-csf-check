# Command line

Everything runs as `python3 -m csfcheck <command>`.

## export

```bash
python3 -m csfcheck export samples/food_bank.json -o out/food_bank.xlsx
```

Scores an answers file, writes the Excel workbook and prints a one-line summary plus the top actions.

- `-o`, `--output`: workbook path (required)
- `--top N`: how many actions to print (default 5)
- `--allow-incomplete`: exit 0 even if some applicable questions are unanswered (otherwise exits 1)

An answers file that doesn't fit the bank (unknown question, invalid score) exits 2.

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

## serve

Runs the web questionnaire and the JSON API in one process.

- `--temp-db`: start a throwaway local PostgreSQL, removed again on Ctrl-C or SIGTERM
- `--database-url`: use an existing database instead (or set `CSFCHECK_DATABASE_URL`)
- `--host`: default `127.0.0.1`
- `--port`: default `23180`
