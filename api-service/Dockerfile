# 1. Base image (Python slim version)
FROM python:3.11-slim

# 2. Set working directory inside container
WORKDIR /app

# 3. Copy dependency file and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copy source code into container
COPY main.py .

# 5. Expose port your app will run on
EXPOSE 5000

# 6. Command to run your app
CMD ["python", "main.py"]
