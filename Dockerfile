FROM python:3.12-slim@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30

ENV PYTHONUNBUFFERED=1 TZ=America/Sao_Paulo UV_LINK_MODE=copy
WORKDIR /app

RUN pip install --no-cache-dir uv==0.13.6
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

ARG APP_REV=dev
ENV APP_REV=${APP_REV} DATA_DIR=/app/data PATH=/app/.venv/bin:$PATH

RUN useradd --create-home --uid 1000 app && mkdir -p /app/data && chown -R app:app /app/data
USER app
VOLUME /app/data

EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --start-period=600s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/health', timeout=2)"

CMD ["uvicorn", "--factory", "getnet_multi_agent.main:create_app", "--host", "0.0.0.0", "--port", "8000"]
