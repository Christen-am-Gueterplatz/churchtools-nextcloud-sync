FROM python:3.14-slim

# Set timezone
ENV TZ=Europe/Berlin
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY main.py .
COPY src/ ./src/

# Idle mode: keep container running for Dokploy schedule tasks
CMD ["tail", "-f", "/dev/null"]
