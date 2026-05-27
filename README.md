# 🍼 BabyCam

**Offline Baby-Monitor für Raspberry Pi** — Bewegungserkennung, Schrei-/Geräuscherkennung, Live-Video & Audio, Telegram-Alarme. 
Alles lokal, keine Cloud, kein Abo.

![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Platform: ARM64](https://img.shields.io/badge/platform-Raspberry%20Pi%20ARM64-red)
![Python: 3.13](https://img.shields.io/badge/python-3.13-blue)

## Features

- 📹 **Live-Video** mit MJPEG-Stream und Motion Detection (OpenCV)
- 🔊 **Live-Audio** im Browser (Web Audio API, ~500ms Latenz)
- 👶 **Schrei-Erkennung** (Frequenzanalyse 300–800 Hz)
- 📢 **Allgemeine Geräuscherkennung** (Lautstärke-basiert)
- 📸 **Snapshots** bei anhaltender Bewegung, Schrei oder Geräusch
- 📱 **Telegram-Benachrichtigung** mit Foto + Setup-Wizard
- 🎛️ **Kamera-Steuerung** live: Helligkeit, Kontrast, Sättigung, Schärfe, Gain
- 🌙 **Nachtmodus** mit automatischer Erkennung + Helligkeitsboost
- 📲 **Mobile-optimiertes** Web-Dashboard (Touch-freundliche Regler)
- 🔔 **Audio-Alarm** im Browser bei Ereignissen
- 🐳 **Docker-Support** für ARM64 (Raspberry Pi 4B / Pi Zero 2 W)
- 💾 **Persistente Konfiguration** in `config.json`

## Hardware

- **Raspberry Pi** (4B oder Zero 2 W, ARM64/aarch64)
- **USB-Webcam** (getestet mit Logitech C930e, ELP 2MP mit IR)
- **USB-Mikrofon** oder Webcam mit eingebautem Mikrofon
- Optional: **IR-Webcam** für Nachtsicht (funktioniert ohne Code-Änderung)

## Schnellstart (Docker)

```bash
# Repo klonen
git clone https://github.com/tobwil/babycam.git
cd babycam

# Docker-Image bauen
docker build -t babycam:latest .

# Mit docker-compose starten
docker compose up -d
```

**Webinterface:** [http://raspberrypi:5000](http://raspberrypi:5000)

In `docker-compose.yml` sind Kamera (`/dev/video0`) und Sound (`/dev/snd`) bereits gemountet.

## Installation ohne Docker

### 1. System-Abhängigkeiten

```bash
# Debian/Raspberry Pi OS
sudo apt update
sudo apt install -y python3 python3-pip python3-venv \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 \
    alsa-utils v4l-utils
```

### 2. Python-Umgebung

```bash
python3 -m venv venv
source venv/bin/activate
pip install opencv-python-headless flask numpy
```

### 3. Kamera & Mikrofon prüfen

```bash
# Verfügbare Kameras
ls /dev/video*

# Verfügbare Mikrofone  
arecord -l

# Mikrofon-Test:
arecord -D plughw:3,0 -f S16_LE -r 16000 -c 1 -d 3 test.wav
aplay test.wav
```

### 4. Starten

```bash
python app.py
```

Öffne [http://localhost:5000](http://localhost:5000) im Browser.

## Konfiguration

Alle Einstellungen im Web-UI unter **⚙️ Alarm** und **📷 Kamera**:

| Einstellung | Default | Beschreibung |
|---|---|---|
| Bewegungs-Empfindlichkeit | 12 | Je niedriger, desto empfindlicher |
| Min. Bewegungsfläche | 800 px² | Ignoriert kleine Bewegungen |
| Geräusch-Schwelle | 0.04 RMS | Lautstärke für Noise-Alert |
| Schrei-Frequenz | 300-800 Hz | Frequenzbereich für Schreien |
| Mindest-Bewegungsdauer | 8s | Snapshots erst nach anhaltender Bewegung |
| Motion-Cooldown | 30s | Mindestabstand zwischen Alerts |
| Kamera Auto/Manuell | Auto | Helligkeit, Kontrast, Sättigung etc. |

Die Konfiguration wird in `config.json` gespeichert und überlebt Neustarts.

### Telegram einrichten

1. **⚙️ Alarm** → Telegram-Toggle einschalten
2. Bot-Token von [@BotFather](https://t.me/BotFather) eingeben (`/newbot`)
3. Dem Bot eine Nachricht senden (`/start`)
4. **🔍 Chat-ID automatisch erkennen** klicken
5. **📱 Test** zum Verifizieren

## Audio-Gerät konfigurieren

Falls dein Mikrofon nicht `plughw:3,0` ist, in `config.json` anpassen:

```json
{
  "audio_device": "plughw:2,0"
}
```

Herausfinden mit: `arecord -l`

## Pi Zero 2 W Setup

Siehe [PI-ZERO-SETUP.md](PI-ZERO-SETUP.md) für eine detaillierte Anleitung zur Einrichtung auf dem Pi Zero 2 W.

## Docker Export / Backup

```bash
# Image exportieren
docker save babycam:latest -o babycam.tar

# Auf anderem System importieren
docker load -i babycam.tar

# ODER komplettes Setup inkl. Konfiguration sichern:
tar -czf babycam-backup.tar.gz \
  babycam/ \
  --exclude='babycam/snapshots' \
  --exclude='babycam/venv'
```

## Projektstruktur

```
babycam/
├── app.py                  # Hauptanwendung (Flask + OpenCV)
├── templates/
│   └── dashboard.html      # Web-Dashboard
├── Dockerfile              # Docker-Image
├── docker-compose.yml      # Docker Compose
├── requirements.txt        # Python-Abhängigkeiten
├── config.json             # Persistente Konfiguration (nicht in Git)
├── snapshots/              # Gespeicherte Snapshots (nicht in Git)
└── PI-ZERO-SETUP.md        # Pi Zero 2 W Anleitung
```

## Technischer Stack

- **Python 3.13** mit Flask (Webserver)
- **OpenCV** für Video-Capture und Motion Detection (Frame-Differencing)
- **NumPy** für Audio-Analyse (RMS, Zero-Crossing Frequenzerkennung)
- **ALSA** (`arecord`) für Mikrofon-Aufnahme
- **v4l2-ctl** für Kamera-Steuerung
- **Web Audio API** für Browser-Audio-Playback
- **Telegram Bot API** für Benachrichtigungen

## Lizenz

MIT — siehe [LICENSE](LICENSE)
