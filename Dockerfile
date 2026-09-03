FROM python:3.11-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Railway injects PORT when present; default 8000 keeps local/docker behavior
CMD sh -c "python -m uvicorn src.web.app:app --host 0.0.0.0 --port ${PORT:-8000}"
