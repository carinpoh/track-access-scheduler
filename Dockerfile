# Track Access Scheduler - container image for Google Cloud Run
FROM python:3.12-slim

# System deps kept minimal; slim image is enough for streamlit + pandas + plotly
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run provides the port to listen on via $PORT (default 8080).
ENV PORT=8080
EXPOSE 8080

# Streamlit must bind to 0.0.0.0 and the Cloud Run port, headless.
CMD streamlit run app.py \
    --server.port=${PORT} \
    --server.address=0.0.0.0 \
    --server.headless=true \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false
