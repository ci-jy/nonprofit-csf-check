FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install . && useradd --create-home csfcheck

COPY samples ./samples
USER csfcheck
EXPOSE 23180

# The database URL comes from CSFCHECK_DATABASE_URL (see docker-compose.yml).
CMD ["python", "-m", "csfcheck", "serve", "--host", "0.0.0.0", "--port", "23180"]
