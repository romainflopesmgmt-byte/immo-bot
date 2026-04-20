FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir httpx beautifulsoup4 python-dotenv

COPY . .

CMD ["python", "main.py"]
