# Base image
FROM python:3.11-slim

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
