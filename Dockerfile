FROM python:3.12-slim

# Install ffmpeg (dibutuhkan yt-dlp untuk memotong video)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install --no-cache-dir -U yt-dlp

COPY bot.py .

CMD ["python", "-u", "bot.py"]
