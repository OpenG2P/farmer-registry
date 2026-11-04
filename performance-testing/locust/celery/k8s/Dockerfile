FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY cases.py db.py preflight.py observe.py run_in_cluster.sh ./
RUN chmod +x /app/run_in_cluster.sh
ENV PYTHONUNBUFFERED=1
CMD ["/app/run_in_cluster.sh"]
