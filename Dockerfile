FROM python:3.14.7-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /build
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
RUN pip install --no-compile .

FROM python:3.14.7-slim-bookworm AS runtime

ENV PATH="/opt/venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/analyzer

RUN groupadd --system --gid 10001 analyzer \
    && useradd --system --uid 10001 --gid analyzer --create-home analyzer

COPY --from=builder --chown=analyzer:analyzer /opt/venv /opt/venv

WORKDIR /data
USER 10001:10001

ENTRYPOINT ["distributed-log-intelligence"]
CMD ["--help"]

