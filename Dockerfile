FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 JOBS_DATA=/data
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY jobsearch ./jobsearch
RUN pip install --no-cache-dir ".[mcp]" \
 && useradd --create-home --uid 1000 jobs \
 && mkdir -p /data && chown jobs /data
USER jobs
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz')"
CMD ["jobsearch", "serve", "--host", "0.0.0.0", "--port", "8000"]
