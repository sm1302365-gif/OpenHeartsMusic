FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (ffmpeg, curl, unzip, git) and deno
RUN apt-get update -y \
    && apt-get install -y --no-install-recommends ffmpeg curl unzip git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://deno.land/install.sh | sh

ENV DENO_INSTALL="/root/.deno"
ENV PATH="${DENO_INSTALL}/bin:${PATH}"

# Install python dependencies from requirements.txt
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . .

# Default entrypoint uses the repo `start` script
ENTRYPOINT ["bash", "start"]
