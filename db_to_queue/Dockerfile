FROM python:3.9-slim

WORKDIR /app

COPY . .

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE ${db_to_queue_CONTAINER_PORT}

# CMD ["python", "db_to_queue.py"]
CMD ["bash", "-c", "sleep 30 && python db_to_queue.py"]
