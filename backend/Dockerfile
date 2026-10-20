FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY novora ./novora

EXPOSE 10000

CMD ["sh", "-c", "exec uvicorn novora.api.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
