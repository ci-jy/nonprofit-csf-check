# Docker Compose

`docker-compose.yml` runs two containers:

- `db`: `postgres:16-alpine` with a named volume (`pgdata`), a `pg_isready` health check and a 256 MB memory limit
- `app`: the image built from the `Dockerfile` (Python 3.12 slim, `pip install .`, runs as a non-root user), which loads the CSF core into the database at startup and serves the questionnaire and the API on port 23180. Memory limit 384 MB.

The app waits for the database's health check before starting. Its own health check calls `/health`.

```bash
docker compose up --build --detach --wait
# open http://127.0.0.1:23180/
docker compose down -v
```

Settings, all optional:

| Variable | Default | What it does |
|---|---|---|
| `CSFCHECK_PORT` | `23180` | Host port, bound to 127.0.0.1 only |
| `CSFCHECK_DB_PASSWORD` | `csfcheck` | Password for the `csfcheck` database user |

Change the password for anything other than a laptop. There's no TLS either. Put a reverse proxy in front if it ever leaves localhost.

## Smoke test

```bash
scripts/compose-smoke.sh
```

This builds and starts the stack on port 23181 under its own project name, so it doesn't touch a running copy. It then takes the food bank through the API: create, answer every question, retake with the new profile, answer the changes, compare, download the workbook. It checks the comparison against the figures in the tests (18 subcategories improved, 3 regressed, 4 actions completed) and runs `docker compose down -v` on exit, including when a step fails.

On the machine I built this on, containers wouldn't start under runc (`open sysctl net.ipv4.ip_unprivileged_port_start file: reopen fd 8: permission denied`). Running the Docker daemon with crun as its default runtime fixed it. That's a host problem, not something in the compose file.
