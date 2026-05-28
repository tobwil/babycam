# BabyCam Docker Image
# Läuft auf Raspberry Pi 4B und Pi Zero 2 W (beide ARM64/aarch64)
FROM python:3.13-slim

LABEL org.opencontainers.image.title="BabyCam"
LABEL org.opencontainers.image.description="Baby Monitor mit Bewegungserkennung und Geräuscherkennung"

# System-Abhängigkeiten für OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0t64 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    alsa-utils \
    v4l-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# piwheels für schnelle ARM-Installation
RUN pip install --no-cache-dir --extra-index-url https://www.piwheels.org/simple \
    opencv-python-headless flask numpy paho-mqtt

COPY app.py .
COPY templates/ templates/
COPY static/ static/

EXPOSE 5000

# Mit --device /dev/video0:/dev/video0 und --device /dev/snd:/dev/snd starten
CMD ["python", "-u", "app.py"]
