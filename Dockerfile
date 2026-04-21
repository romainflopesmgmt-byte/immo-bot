FROM python:3.12-slim

WORKDIR /app

# curl pour les scrapers (TLS fingerprint normal)
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir httpx beautifulsoup4 python-dotenv

COPY . .

CMD ["python", "main.py"]
