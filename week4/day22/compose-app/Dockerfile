FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/app/deps -r requirements.txt

FROM python:3.11-slim AS runtime
WORKDIR /app
COPY --from=builder /app/deps /app/deps
COPY app.py .
ENV PYTHONPATH=/app/deps
RUN useradd --create-home --shell /bin/bash appuser \
 && chown -R appuser:appuser /app
USER appuser
EXPOSE 5000
CMD ["python", "app.py"]