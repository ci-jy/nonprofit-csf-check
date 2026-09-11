# API

The API is FastAPI on PostgreSQL. Interactive docs are at `/docs` once it is running.

![FastAPI docs for the csfcheck API](api-docs.png)

## Starting it

Against a throwaway database (stopped and deleted on Ctrl-C):

```bash
python3 -m csfcheck serve --temp-db --port 23180
```

Against your own database:

```bash
export CSFCHECK_DATABASE_URL='postgresql+psycopg://user@localhost/csfcheck'
python3 -m csfcheck load-csf
python3 -m csfcheck serve
```

`load-csf` and `serve` also take `--database-url`. `serve` takes `--host` (default `127.0.0.1`) and `--port` (default 23180).

## Endpoints

- `GET /health`
- `GET /profile-flags`
- `POST /organisations`: name and profile flags
- `POST /organisations/{id}/assessments`: returns the assessment ID and its token
- `GET /assessments/{id}/next?limit=N`: the next unanswered questions
- `POST /assessments/{id}/answers`: answers, with optional evidence notes
- `GET /assessments/{id}/profile`: current vs target per subcategory
- `GET /assessments/{id}/action-plan?limit=N`
- `GET /assessments/{id}/workbook`: the Excel workbook

Everything under `/assessments` needs the `X-Assessment-Token` header.

## Example session

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

## Behaviour worth knowing

- The per-assessment token is the only access control. Only its SHA-256 is stored.
- Answering a question that the profile or an earlier answer skips returns 422.
- If you lower a parent answer, the follow-up answers it no longer allows are dropped.
- `next` returns questions in bank order and waits on a follow-up's parent, so it can return fewer than `limit` while answers are pending.
