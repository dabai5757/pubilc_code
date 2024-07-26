FROM python:3.9-slim

WORKDIR /app

COPY . .

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 5005

CMD ["python", "db_to_queue.py"]
