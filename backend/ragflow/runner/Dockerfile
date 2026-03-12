FROM python:3.11-slim

# System deps (adjust for your needs)
RUN apt-get update && apt-get install -y build-essential git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project and install dependencies
COPY . /app
RUN pip install --no-cache-dir .

# Make scripts executable
RUN chmod +x /app/scripts/*.py

ENV PYTHONUNBUFFERED=1
# Runner will execute the python scripts via RagFlow commands, so keep a shell entrypoint.
ENTRYPOINT ["bash", "-lc"]