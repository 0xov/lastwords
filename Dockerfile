FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py seed_words.py cloud_persistence.py ./
COPY static ./static

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]
