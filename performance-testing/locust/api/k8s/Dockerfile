FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir locust requests
COPY . /app
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
WORKDIR /app
