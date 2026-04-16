FROM python:3.12-slim

WORKDIR /app

COPY server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY server/ ./

ENV DOORPLATE_DATA_DIR=/app/data
RUN mkdir -p /app/data

EXPOSE 5000

CMD ["python", "server.py"]
