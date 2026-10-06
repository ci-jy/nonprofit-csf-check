# Changelog

## 0.3.0 - Reassessment comparison and Docker Compose stack

- Assessments are versioned. A retake (`POST /assessments/{id}/retake` or the Retake link on the overview) starts the next version from a copy of the answers and evidence, with its own profile flags, and keeps the same token. Older databases get the new columns at startup.
- `compare.py` compares two versions: subcategories improved, regressed, now applicable or no longer applicable, the old plan's actions completed, progressed or still open, new actions, and changed answers. A Hypothesis property checks that raising answers never shows a regression.
- `GET /assessments/{id}/versions` and `GET /assessments/{id}/compare`, and a progress page in the web questionnaire.
- Progress sheet in the Excel workbook (a baseline on a first assessment), and a "Progress since ..." section in the Word report. `export` and `report` take `--previous`.
- A second food bank assessment in `samples/retakes/`.
- `Dockerfile` and `docker-compose.yml` (PostgreSQL 16 and the app, with health checks and memory limits), and `scripts/compose-smoke.sh`, which retakes a sample over the API against the stack and tears it down.
- A sample workbook and Word report in `docs/samples/` (`scripts/build_doc_samples.py`), with screenshots of the progress page, the retake form, the Progress sheet and the report.

## 0.2.0 - Web questionnaire, profile heat map and Word findings report

- Server-rendered questionnaire (FastAPI and Jinja templates), one CSF function per page, with a progress bar, plain-language help under every question, an optional evidence box, follow-ups that open on the same page and a list of the questions that were skipped and why.
- Every question in `questions.yaml` now carries a `help` text, and the bank is rejected at startup without one.
- Function-by-category heat map of current against target, drawn as SVG on the server, and an action plan page.
- Word findings report (python-docx) with an executive summary, profile tables and top actions, from the web pages or `python3 -m csfcheck report`.
- Assessment token held in a per-assessment cookie, with a one-time resume code.
- Answer saving moved into `db.store_answers`, shared by the API and the pages.
- Fixed: `serve --temp-db` left its PostgreSQL cluster running when stopped with SIGTERM.

## 0.1.0 - Assessment engine, API and Excel workbook

- NIST CSF 2.0 core loaded from the vendored CPRT export, checked against its SHA-256, into PostgreSQL.
- Question bank with profile branching and follow-ups, checked for coverage over every profile.
- Current-vs-target scoring with Quick-Start targets and a ranked action plan.
- FastAPI JSON API with a per-assessment token, and the Excel workbook export.
- Three sample organisations.
