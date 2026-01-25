# Base image
FROM python:3.11-slim

# Working directory
WORKDIR /app

# Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application
COPY worker.py .

# Run (no exposed port; worker consumes from queue only)
CMD ["python", "-u", "worker.py"]
