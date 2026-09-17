# Changelog

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
