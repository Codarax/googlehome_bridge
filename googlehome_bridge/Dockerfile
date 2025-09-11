# Start with the base image
FROM ghcr.io/home-assistant/amd64-base:latest

# Set the working directory
WORKDIR /app

# Install Python and pip
RUN apk update && apk add --no-cache python3 py3-pip

# Copy requirements file
COPY requirements.txt ./

# Install Python dependencies using pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .