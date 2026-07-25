FROM python:3.11-slim

# System deps for matplotlib / Pillow / mplsoccer
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libfontconfig1 \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

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

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
