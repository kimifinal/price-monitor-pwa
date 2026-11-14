# Price Monitor — backend container
# Base image: python:3.11-slim (Ubuntu 24.04)

FROM python:3.11-slim

# ---- build-time: C deps needed by lxml / pydantic-core / uvloop ----
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc g++ && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ---- install Python deps first (layer caching) ----
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt \
    && pip install --no-cache-dir 'uvicorn[standard]'

# ---- copy project code ----
COPY backend/ /app/backend/
COPY scripts/ /app/scripts/

WORKDIR /app/backend

# Expose the API
EXPOSE 8000

# Default command: start the FastAPI server
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
