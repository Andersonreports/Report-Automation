# Anderson Report Automation – Docker Image
# Build:  docker build -t anderson-reports .
# Run:    docker run -p 8000:8000 anderson-reports

FROM python:3.11-slim

WORKDIR /app

# ── System dependencies (fonts, image libs) ────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

# ── Python dependencies ────────────────────────────────────────────────────────
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# ── Backend Python files ───────────────────────────────────────────────────────
COPY backend/ /app/backend/

# ── Frontend HTML / JS / CSS / assets ─────────────────────────────────────────
COPY frontend/ /app/frontend/

# ── Create runtime directories ─────────────────────────────────────────────────
RUN mkdir -p \
    /app/backend/reports \
    /app/backend/reports-pgta \
    /app/backend/reports-karyotype \
    /app/backend/temp \
    /app/backend/drafts/TERA \
    /app/backend/drafts/PGTA \
    /app/backend/uploads/pgta_cnv

# ── Environment ────────────────────────────────────────────────────────────────
ENV FRONTEND_DIR=/app/frontend
ENV PYTHONUNBUFFERED=1

WORKDIR /app/backend

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
