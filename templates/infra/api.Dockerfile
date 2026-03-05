# ---- Stage 1: Builder ----
FROM python:<< python_version >>-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Stage 2: Production ----
FROM python:<< python_version >>-slim
RUN addgroup --system appgroup && adduser --system --group appuser
WORKDIR /app
COPY --from=builder /install /usr/local
COPY ./app.py ./app.py
USER appuser
EXPOSE << api_port >>
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:<< api_port >>/')"
CMD ["uvicorn", "app:app", "--host", "<< api_host >>", "--port", "<< api_port >>"]
