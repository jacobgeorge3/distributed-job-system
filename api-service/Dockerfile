# Base image
FROM python:3.11-slim

# Install curl for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Working directory
WORKDIR /app

# Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application
COPY main.py .

# Expose HTTP port
EXPOSE 5000

# Run
CMD ["python", "-u", "main.py"]
