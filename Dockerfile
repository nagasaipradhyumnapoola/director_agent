FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN pip install --no-cache-dir -e . --no-deps \
    && pip install --no-cache-dir "mcp>=1.0" python-docx

# Run as an unprivileged user (65534 is the image's nobody account).
USER 65534:65534
WORKDIR /project

ENTRYPOINT ["python", "-m", "director"]
CMD ["--help"]
