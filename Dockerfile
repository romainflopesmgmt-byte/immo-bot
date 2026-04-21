FROM python:3.12-slim

WORKDIR /app

# Deps systeme pour curl_cffi
RUN apt-get update && apt-get install -y --no-install-recommends \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir httpx beautifulsoup4 python-dotenv && \
    pip install --no-cache-dir curl_cffi || echo "WARN: curl_cffi failed, continuing without it"

COPY . .

CMD ["python", "main.py"]
