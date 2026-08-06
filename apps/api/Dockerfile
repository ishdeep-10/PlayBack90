FROM python:3.11-slim

# System deps for matplotlib / Pillow / mplsoccer
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libfontconfig1 \
    fonts-dejavu-core \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Firefox ESR + geckodriver for the live WhoScored scrape path
# (Data/extract_opta_data.py looks for /usr/bin/firefox-esr and /usr/local/bin/geckodriver first).
RUN apt-get update && apt-get install -y --no-install-recommends firefox-esr \
    && rm -rf /var/lib/apt/lists/* \
    && curl -sSL https://github.com/mozilla/geckodriver/releases/download/v0.34.0/geckodriver-v0.34.0-linux64.tar.gz \
    | tar -xz -C /usr/local/bin \
    && chmod +x /usr/local/bin/geckodriver

WORKDIR /app

# Install Python dependencies
COPY apps/api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Keep the runtime image focused while preserving model feature builders and
# the WhoScored importer used by live jobs.
COPY apps/api /app/repo/apps/api
COPY Data /app/repo/Data
COPY models /app/repo/models
COPY player_images_map.json /app/repo/player_images_map.json
COPY SoccerWiki*Player\ Data*.json /app/repo/

WORKDIR /app/repo/apps/api

ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
