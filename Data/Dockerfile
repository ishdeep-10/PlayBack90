FROM python:3.10-slim

ENV PYTHONUNBUFFERED=1 \
    MOZ_HEADLESS=1

WORKDIR /playback90/Data

# System + Firefox + Geckodriver + required libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg2 ca-certificates firefox-esr \
    libgtk-3-0 libdbus-glib-1-2 libasound2 xvfb \
    gcc && \
    wget -q https://github.com/mozilla/geckodriver/releases/download/v0.36.0/geckodriver-v0.36.0-linux64.tar.gz && \
    tar -xzf geckodriver-v0.36.0-linux64.tar.gz -C /usr/local/bin && \
    rm geckodriver-v0.36.0-linux64.tar.gz && \
    rm -rf /var/lib/apt/lists/*

# Python deps first (leverage layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# (Optionally ensure scripts are executable)
RUN chmod +x run_all.py

CMD ["python", "run_all.py"]