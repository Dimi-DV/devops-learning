# ---- Stage 1: builder ----
FROM python:3.11-slim AS builder

WORKDIR /app

# install dependencies into a specific directory we can copy out later
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/app/deps -r requirements.txt


# ---- Stage 2: runtime ----
FROM python:3.11-slim AS runtime

WORKDIR /app

# copy installed dependencies from the builder stage
COPY --from=builder /app/deps /app/deps

# copy app code from the host
COPY app.py .

# tell Python where to find the dependencies
ENV PYTHONPATH=/app/deps

# create a non-root user and drop to it
RUN useradd --create-home --shell /bin/bash appuser \
 && chown -R appuser:appuser /app
USER appuser

ENV APP_VERSION=1.0.0
EXPOSE 5000

CMD ["python", "app.py"]