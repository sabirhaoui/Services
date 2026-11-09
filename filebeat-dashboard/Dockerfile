FROM python:3.14.0-slim
WORKDIR /app
COPY requirements.lock .
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home observer && mkdir /data && chown observer /data
COPY src/filebeat /app/filebeat
COPY contracts /contracts
USER observer
ENV DB_PATH=/data/events.db
CMD ["uvicorn", "filebeat.api:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log"]
