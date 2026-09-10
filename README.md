# csfcheck: a NIST CSF 2.0 self-assessment for small non-profits

Picture the office manager at a neighbourhood food bank. Their funder has
started asking "what are you doing about cybersecurity?", the board treasurer
has heard about ransomware, and the spreadsheet of client households sits in a
shared Google Drive that a dozen volunteers can open. Nobody there is a security
person. The standard answers don't fit them. A risk assessment under NIST SP 800-30
or ISO 27001 assumes a security team, documented processes and a budget for tools
or consultants. So the assessment never happens, and the organisation can't
show an auditor or funder what it does to protect donor and client data.
[This study of NGO cybersecurity](https://www.emerald.com/insight/content/doi/10.1108/TG-08-2024-0201/full/html)
describes that gap, and NIST's own
[CSF 2.0 Small Business Quick-Start Guide](https://www.nist.gov/publications/nist-cybersecurity-framework-20-small-business-quick-start-guide)
says it is meant to help "other relatively small organizations, such as
non-profits".

csfcheck is my attempt at the missing middle step. It's a guided
self-assessment that someone who isn't an expert can finish. It asks plain-language
questions, skips the ones that don't apply to the organisation, scores the answers
against the CSF 2.0 outcomes and returns:

- a **current vs target profile** for all 106 CSF 2.0 subcategories,
- a **ranked action plan**, cheapest risk reduction first, with each action's
  wording taken from NIST's own implementation examples,
- an **Excel workbook** an auditor can work from: Summary, Profile, Gaps,
  Action Plan and an Evidence Log with columns for the auditor to fill in.

It's meant for executive directors, office managers and volunteer IT people at
small charities and student societies, and for junior IT risk or audit staff
who assess them. It doesn't scan anything, and it isn't a certification (ISO
27001, SOC 2 or anything else). It records what the organisation says it does,
and the evidence it offers.

## How it works

**The CSF core comes from NIST's data.** `src/csfcheck/data/csf-2.0-core.json`
is the JSON export of CSF 2.0 from NIST's Cybersecurity and Privacy Reference
Tool (CPRT). Its SHA-256 is stored next to it, and both the loader and the
in-memory catalog refuse a file that doesn't match. The export also carries the
withdrawn CSF 1.1 subcategories, so those are dropped. What's left is 6
functions, 22 categories, 106 subcategories and 363 implementation examples.
`python -m csfcheck load-csf` imports them into PostgreSQL, and the API reads
its catalog back from there.

**The question bank is `src/csfcheck/data/questions.yaml`.** It has 100
questions. Each one maps to one or more subcategories and uses a four-step
answer scale ("No, or not sure" = 0 up to "Yes, written down and checked at
least once a year" = 3). Questions branch in two ways:

- `when:` is a condition on ten profile flags (`has_office`, `has_servers`,
  `uses_cloud_email`, `takes_payments`, `remote_staff`, `holds_donor_data`,
  `holds_client_data`, `has_employees`, `uses_it_provider`,
  `develops_software`), written as a small boolean expression such as
  `has_office or has_servers`. A student club with no premises is never asked
  about door codes or a server's disk health.
- `requires:` opens a follow-up only after its parent scored well enough. If
  you have no backups, you aren't asked whether you test them. The follow-up
  then scores 0.

Some subcategories don't apply to some organisations, for example secure
software development when you write no code. Each of those has an explicit
`exclusions:` rule with a reason, which ends up in the workbook. At startup the
bank is checked against all 1,024 combinations of profile flags. In every
combination, each subcategory must be either asked about or excluded by a rule,
never both and never neither. A typo in a flag name, a mapping to a CSF 1.1 ID
or a gap in coverage stops the app before it serves anything.

**Targets come from the Quick-Start Guide.** `quickstart.yaml` lists the
guide's 41 "Actions to Consider" with the CSF references printed next to them.
A subcategory the guide names directly gets target 3. One inside a category the
guide names gets 2, and the rest get 1 (at least done informally). That gives
38 / 17 / 51 subcategories at each level.

**Scoring and ranking** (`engine.py`, `risk_model.yaml`):

| Quantity | How it's computed |
|---|---|
| current | mean answer score of the applicable questions mapped to the subcategory (unanswered = 0) |
| gap | `max(0, target - current)` |
| likelihood | `1 + (inherent likelihood - 1) * gap / target`: a closed gap leaves 1 |
| impact | category's inherent impact, raised by profile flags (donor data, client data, payments, servers) |
| risk | likelihood × impact (1–25), rated Low / Medium / High / Critical |
| action priority | risk reduced by closing the gap ÷ cost-band weight (free 1, low 2, medium 3, high 5) |

The inherent likelihood, impact and cost band for each category are my own
coarse judgements for a small charity, kept in one YAML file so they're easy
to argue with. The design rule that matters is that improving an answer can
never raise any risk score. A Hypothesis property test checks that.

## What it found for the three sample organisations

`samples/` holds three made-up organisations modelled on the kinds of NGO in
the study: a small food bank with client records, a student club that runs
everything on members' own laptops, and an arts charity with a NAS, an IT
freelancer and online donations.

| Sample | Questions asked (of 100) | Skipped by profile | Follow-ups skipped | Subcategories not applicable | At target | Actions |
|---|---|---|---|---|---|---|
| Riverside Community Food Bank | 86 | 10 | 4 | 2 | 19 | 85 |
| Campus Robotics Society | 81 | 12 | 7 | 5 | 11 | 90 |
| Harbour Lights Arts Trust | 94 | 3 | 3 | 2 | 51 | 53 |

On average 13% of the bank is skipped (19% for the student club). That's less
than I expected when I started. Most of the CSF is governance and incident
handling, which applies to every organisation however small. The skipped share
mostly reflects how much infrastructure an organisation *doesn't* have. For all
three samples, every one of the top ten actions costs nothing but time. For the
food bank and the student club the top action is the same: know who you must
notify after a breach (RS.CO-02).

![Top of the Action Plan sheet for the food bank sample](docs/action-plan.png)

*The first ten rows of the Action Plan sheet in `out/food_bank.xlsx`, rendered
to an HTML table with headless Chrome. The workbook itself also has owner and
status columns, with a dropdown for status.*

The API comes with FastAPI's interactive docs:

![FastAPI docs for the csfcheck API](docs/api-docs.png)

## Running it

You need Python 3.11+ and PostgreSQL. The tests and `serve --temp-db` start
their own throwaway cluster from the local `initdb`/`pg_ctl`, so PostgreSQL
only has to be installed, not running. I've been using Python 3.14 and
PostgreSQL 18 on Ubuntu.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'

python3 -m pytest                      # 50 tests, including the PostgreSQL and API ones
python3 -m csfcheck check              # checksum, catalog counts, bank coverage
python3 -m csfcheck export samples/food_bank.json -o out/food_bank.xlsx
python3 -m csfcheck stats samples/*.json
```

`export` prints a summary and the top five actions:

```
Riverside Community Food Bank: asked 86 of 100 questions (14.0% skipped), 104 subcategories assessed, 85 actions
   1. RS.CO-02  High     free   Follow the organization's breach notification procedures after discovering a dat
   2. RS.CO-03  High     free   Securely share information consistent with response plans and information sharin
   3. PR.AT-01  High     free   Provide basic cybersecurity awareness and training to employees, contractors, pa
   4. PR.AT-02  High     free   Identify the specialized roles within the organization that require additional c
   5. ID.AM-03  High     free   Maintain baselines of communication and data flows within the organization's wir
wrote out/food_bank.xlsx
```

To run the API against a throwaway database (stopped and deleted again on Ctrl-C):

```bash
python3 -m csfcheck serve --temp-db --port 23180
```

or against your own database:

```bash
export CSFCHECK_DATABASE_URL='postgresql+psycopg://user@localhost/csfcheck'
python3 -m csfcheck load-csf
python3 -m csfcheck serve
```

A session looks like this:

```bash
curl -s -X POST localhost:23180/organisations -H 'content-type: application/json' \
  -d '{"name":"Riverside Community Food Bank","profile":{"has_office":true,"uses_cloud_email":true,"holds_donor_data":true,"holds_client_data":true,"has_employees":true}}'
curl -s -X POST localhost:23180/organisations/1/assessments
# -> {"id":1,"token":"...","questions_for_profile":90}
curl -s 'localhost:23180/assessments/1/next?limit=2' -H "X-Assessment-Token: $TOKEN"
curl -s -X POST localhost:23180/assessments/1/answers -H "X-Assessment-Token: $TOKEN" \
  -H 'content-type: application/json' \
  -d '{"answers":[{"question_id":"gv-mission","value":"mostly"},{"question_id":"gv-dependencies","value":"informal","evidence":"List of logins kept by the coordinator"}]}'
curl -s 'localhost:23180/assessments/1/action-plan?limit=1' -H "X-Assessment-Token: $TOKEN"
curl -s localhost:23180/assessments/1/workbook -H "X-Assessment-Token: $TOKEN" -o assessment.xlsx
```

The only access control is the per-assessment token returned when the
assessment is created. Only its SHA-256 is stored. Answering a question that
the profile or an earlier answer skips gets a 422. If you lower a parent answer,
the follow-up answers it no longer allows are dropped.

## Tests

- `test_properties.py` (Hypothesis): for random profiles, every subcategory is
  either reachable or excluded by a stated rule. Walking random answers through
  the question flow never yields a skipped question. Improving any single
  answer never raises any subcategory's risk or the total.
- `test_api.py`: each sample completes through the API on PostgreSQL. The API
  asks exactly the questions the sample answers, the plan comes back ranked,
  and the downloaded workbook has the right sheets, row counts and evidence
  notes. It also covers token checks and rejection of skipped questions.
- `test_workbook_export.py`: runs the CLI export for each sample and checks
  headers, the 106-row profile, gap ordering and one action per gap.
- `test_questions.py`: a broken bank is rejected for each kind of error.

## Known issues and next steps

- The likelihood/impact numbers are judgement, not data. They're consistent and
  easy to change, but two people could reasonably set them differently. The
  ranking depends far more on gap size and cost band than on them.
- The action plan is long (53–90 actions), one per subcategory gap. The
  Now / Next / Later horizon only goes by rank. Grouping related actions (all
  the incident-response ones, say) into one task would make it easier to read.
- Answers are averaged per subcategory, so a strong answer can hide a weak one
  on the same subcategory. Using the minimum would be stricter but harsher on
  small organisations.
- The 13% skip rate comes from three samples, not from real organisations.
- Next: a web questionnaire so nobody needs curl, a heat map of the profile
  and a Word findings report (python-docx). After that, comparing a
  reassessment with the previous one, and a Docker Compose stack with
  PostgreSQL.

## Data and licences

- NIST CSF 2.0 core: NIST CPRT JSON export (`csf_2_0_0`), public domain as a
  work of the US government.
- Target priorities: NIST SP 1300, *NIST Cybersecurity Framework 2.0: Small
  Business Quick-Start Guide* (https://doi.org/10.6028/NIST.SP.1300). The
  action texts in `quickstart.yaml` are shortened from the guide.
- No paid or third-party mapping data is used. The sample organisations are
  fictional.
