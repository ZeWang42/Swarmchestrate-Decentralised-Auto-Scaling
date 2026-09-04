FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY PID.py .
COPY queue_das_logging.py .
COPY execution ./execution
COPY monitoring ./monitoring
COPY utils ./utils

CMD ["python", "PID.py"]
