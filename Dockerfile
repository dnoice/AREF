FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl && \
    rm -rf /var/lib/apt/lists/*

# Copy everything first (source needed for hatchling build)
COPY . .

# Install the package
RUN pip install --no-cache-dir .

EXPOSE 8080

# Default command (overridden per-service in docker-compose)
CMD ["uvicorn", "aref.dashboard.app:app", "--host", "0.0.0.0", "--port", "8080"]
