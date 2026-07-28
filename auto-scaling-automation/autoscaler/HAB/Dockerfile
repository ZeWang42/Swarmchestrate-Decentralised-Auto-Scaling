FROM python:3.11-slim

WORKDIR /app

# copy code
COPY . /app

# install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# run DAS
CMD ["python", "HAB.py"]
