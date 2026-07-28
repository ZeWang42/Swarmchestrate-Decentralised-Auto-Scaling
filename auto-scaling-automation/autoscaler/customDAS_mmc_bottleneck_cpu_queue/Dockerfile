FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY DAS.py .
COPY queue_das_logging.py .
COPY p2pAgent.py .
COPY execution ./execution
COPY monitoring ./monitoring
COPY utils ./utils

CMD ["python", "DAS.py"]
