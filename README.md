# 🍼 BabyCam

**Offline Baby-Monitor für Raspberry Pi** — Bewegungserkennung, Schrei-/Geräuscherkennung, Live-Video & Audio, Telegram-Alarme, Home Assistant Integration.

Alles lokal. Keine Cloud. Kein Abo. Kein Internet nötig.

![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Platform: ARM64](https://img.shields.io/badge/platform-Raspberry%20Pi%20ARM64-red)
![Python: 3.13](https://img.shields.io/badge/python-3.13-blue)

---

## 📋 Inhaltsverzeichnis

- [Features](#features)
- [Hardware](#hardware)
- [Schnellstart](#schnellstart)
  - [Pi 4B (Hauptgerät)](#pi-4b-hauptgerät)
  - [Pi Zero 2 W (Nebenstellen-Gerät)](#pi-zero-2-w-nebenstellen-gerät)
  - [Multi-Instanz-Setup](#multi-instanz-setup)
- [Konfiguration](#konfiguration)
  - [Web-UI](#web-ui)
  - [config.json Referenz](#configjson-referenz)
- [Home Assistant Integration](#home-assistant-integration)
  - [MQTT-Sensoren](#mqtt-sensoren)
  - [Kamera](#kamera)
  - [Automatisierungs-Beispiele](#automatisierungs-beispiele)
- [Telegram-Benachrichtigungen](#telegram-benachrichtigungen)
- [API-Referenz](#api-referenz)
- [Fehlerbehebung](#fehlerbehebung)
- [Update](#update)
- [Backup & Export](#backup--export)
- [Projektstruktur](#projektstruktur)
- [Lizenz](#lizenz)

---

## Features

- 📹 **Live-Video** — MJPEG-Stream mit Motion Detection (OpenCV Frame-Differencing)
- 🔊 **Live-Audio** — Web Audio API im Browser, ~500ms Latenz
- 👶 **Schrei-Erkennung** — Frequenzanalyse im 300–800 Hz-Bereich
- 📢 **Geräuscherkennung** — Lautstärke-basiert, mit einstellbarer Mindestdauer
- 📸 **Snapshots** — Automatisch bei anhaltender Bewegung, Schrei oder Geräusch
- 📱 **Telegram-Alarme** — Push-Benachrichtigung mit Snapshot-Foto
- 🎛️ **Kamera-Steuerung live** — Helligkeit, Kontrast, Sättigung, Schärfe, Gain (via v4l2-ctl)
- 🌙 **Nachtmodus** — Automatische Erkennung + Helligkeitsboost für Snapshots
- 📲 **Mobile-optimiertes Dashboard** — Touch-freundliche Regler, Dark Mode
- 🏠 **Home Assistant Integration** — MQTT Auto-Discovery + Generic Camera
- 🔔 **Audio-Alarm** — Browser-Alarmton bei Ereignissen
- 🐳 **Docker** — ARM64-Image, separate Compose-Files für Pi 4B und Pi Zero
- 💾 **Persistente Konfiguration** — `config.json`, überlebt Neustarts und Updates
- 🔧 **Debug-Endpoint** — `/api/debug` mit Live-Status, MQTT-Info und Ereignis-Log

---

## Hardware

| Komponente | Empfehlung | Alternativen |
|---|---|---|
| **Raspberry Pi** | Pi Zero 2 W (sparsam, klein) | Pi 4B, Pi 3B |
| **Kamera** | Logitech C930e (1080p, Autofokus, gutes Mikro) | ELP 2MP mit IR, jede UVC-Webcam |
| **SD-Karte** | ≥ 8 GB | — |

Getestete Kombinationen:

- ✅ Pi Zero 2 W + Logitech C930e (5 FPS, ~50% CPU)
- ✅ Pi 4B + Logitech C930e (15 FPS, ~25% CPU)
- ✅ Pi 4B ohne Kamera (reine Audio-Instanz für MQTT-Backup)

---

## Schnellstart

### Voraussetzungen (alle Plattformen)

- Raspberry Pi mit **Raspberry Pi OS Lite (64-bit)**
- Docker & Docker Compose installiert: `curl -fsSL https://get.docker.com | sh && sudo apt install -y docker-compose-plugin`
- Benutzer in `docker`- und `audio`-Gruppen: `sudo usermod -aG docker,audio $USER`

### Pi 4B (Hauptgerät)

```bash
git clone https://github.com/tobwil/babycam.git
cd babycam

# Mikrofon finden
arecord -l
# → Card-Nummer merken (C930e meist Card 3)

# config.json anpassen (audio_device)
nano config.json
# → "audio_device": "plughw:3,0"

# MQTT-Broker setzen (für Home Assistant)
# In docker-compose.yml:
#   MQTT_BROKER=192.168.178.131

# Bauen & starten
docker build -t babycam:latest .
docker compose up -d
```

**Webinterface:** `http://<pi-ip>:5000`

### Pi Zero 2 W (Nebenstellen-Gerät)

Der Pi Zero hat eine schwächere CPU. Deshalb gibt es ein spezielles Compose-File, das `/dev/video0` als Device-Mount (nicht Volume) einbindet — Volume-Mounts für Device-Dateien funktionieren auf dem Zero nicht zuverlässig.

```bash
git clone https://github.com/tobwil/babycam.git
cd babycam

# Mikrofon finden
arecord -l
# → C930e am Zero meist Card 1 (nicht Card 3!)

# config.json anpassen
nano config.json
# → "audio_device": "plughw:1,0"
# → "fps": 5                     # Zero packt max. ~5 FPS

# MQTT-Broker setzen
# In docker-compose.pi-zero.yml:
#   MQTT_BROKER=192.168.178.131

# Bauen & starten
docker build -t babycam:latest .
docker compose -f docker-compose.pi-zero.yml up -d
```

> ⚠️ **Wichtig:** Immer `docker-compose.pi-zero.yml` verwenden, nicht das Standard-Compose-File! Dieses nutzt `devices:` statt Volume-Mounts für `/dev/video0`.

### Multi-Instanz-Setup

Typisches Setup: Ein Pi Zero 2 W im Kinderzimmer (mit Kamera), ein Pi 4B als Home Assistant + Backup-Instanz.

```
┌─────────────────────┐     MQTT      ┌─────────────────────┐
│   Pi Zero 2 W       │◄─────────────►│   Pi 4B             │
│   192.168.178.130   │               │   192.168.178.131   │
│                     │               │                     │
│  📹 Kamera + 🎤     │               │  🏠 Home Assistant  │
│  5 FPS, 640×480     │               │  📡 Mosquitto MQTT  │
│  MQTT → HA          │               │  🎤 Audio-Backup    │
└─────────────────────┘               └─────────────────────┘
```

**Pi 4B Backup-Instanz** (ohne Kamera, nur Audio + MQTT):

```bash
# docker-compose.pi-one.yml verwendet — keine /dev/video0-Mounts!
docker compose -f docker-compose.pi-one.yml up -d
```

Diese Instanz sendet Audio-Pegel und Geräuscherkennung per MQTT, auch wenn die Zero-Instanz ausfällt. Die Kamera-Entität in Home Assistant bleibt dann ohne Bild, aber die Audio-Sensoren laufen weiter.

---

## Konfiguration

### Web-UI

Alle Einstellungen im Browser unter:

- **⚙️ Alarm** — Bewegung, Geräusch, Schrei, Nachtmodus, Telegram
- **📷 Kamera** — FPS, Helligkeit, Kontrast, Sättigung, Schärfe, Gain

Änderungen werden **sofort** übernommen (kein Neustart nötig). 💾 Speichern persistiert in `config.json`.

### config.json Referenz

```jsonc
{
  // ── Bewegungserkennung ──
  "motion_threshold": 12,        // Empfindlichkeit (2–50, niedriger = sensibler)
  "motion_min_area": 800,        // Minimale Bewegungsfläche in px²
  "motion_duration_min": 8,      // Sekunden anhaltende Bewegung für Snapshot
  "alert_cooldown_motion": 30,   // Sekunden Pause zwischen Bewegungs-Alarmen

  // ── Geräuscherkennung ──
  "sound_threshold": 0.04,       // RMS-Lautstärkeschwelle (0.01 = Flüstern)
  "cry_freq_low": 300,           // Untere Frequenz für Schreien (Hz)
  "cry_freq_high": 800,          // Obere Frequenz für Schreien (Hz)
  "cry_duration": 1.5,           // Sekunden anhaltendes Schreien für Alarm
  "noise_alert_enabled": true,   // Auch auf andere Geräusche alarmieren
  "noise_duration": 1.0,         // Sekunden anhaltendes Geräusch
  "alert_cooldown_cry": 60,      // Sekunden Pause zwischen Schrei-Alarmen

  // ── Kamera ──
  "camera_device": 0,            // /dev/videoX (0 = erste Kamera)
  "frame_width": 640,            // Bildbreite
  "frame_height": 480,           // Bildhöhe
  "fps": 15,                     // Ziel-FPS (Pi Zero: max 5)

  // ── Kamera-Bildsteuerung ──
  "camera_auto": true,           // Auto-Modus (ignoriert manuelle Werte)
  "camera_brightness": 128,      // 0–255
  "camera_contrast": 128,        // 0–255
  "camera_saturation": 128,      // 0–255
  "camera_sharpness": 128,       // 0–255
  "camera_gain": 0,              // 0–100

  // ── Audio ──
  "audio_device": "plughw:3,0",  // arecord -l → Card-Nummer
  "audio_rate": 16000,           // Samplerate (8000–48000 Hz)

  // ── Modi ──
  "night_mode_auto": true,       // Automatischer Nachtmodus
  "night_brightness_threshold": 40, // Helligkeit < 40 = Nacht
  "snapshot_quality": 75,        // JPEG-Qualität (1–100)
  "video_enabled": true,         // Live-Video-Stream
  "audio_enabled": true,         // Live-Audio & Pegel

  // ── Telegram ──
  "telegram_enabled": false,
  "telegram_bot_token": "",
  "telegram_chat_id": ""
}
```

> 💡 **Pi Zero 2 W Tipp:** `fps: 5`, `audio_rate: 16000`, `video_enabled: true` (aber Kamera-Automatik an). CPU-Auslastung ~50%.

---

## Home Assistant Integration

### Voraussetzungen

- **Mosquitto MQTT Broker** in Home Assistant (Einstellungen → Add-ons → Mosquitto)
- BabyCam und HA im selben Netzwerk
- `MQTT_BROKER` im docker-compose.yml auf die HA-IP gesetzt

### MQTT-Sensoren

Nach dem Start erscheinen **automatisch** via MQTT Auto-Discovery:

| Sensor | Typ | Topic | Beschreibung |
|---|---|---|---|
| `binary_sensor.babycam_bewegung` | Motion | `babycam/motion` | Bewegung (Frame-Differencing) |
| `binary_sensor.babycam_schreien` | Sound | `babycam/cry` | Schreien (300–800 Hz) |
| `binary_sensor.babycam_gerausch` | Sound | `babycam/noise` | Allgemeines Geräusch |
| `binary_sensor.babycam_nachtmodus` | Light | `babycam/night_mode` | Automatische Nachterkennung |
| `sensor.babycam_lautstarke` | RMS | `babycam/sound_level` | Aktueller Lautstärkepegel |
| `sensor.babycam_helligkeit` | px | `babycam/brightness` | Durchschnittliche Bildhelligkeit |

Keine YAML-Konfiguration nötig — die Sensoren registrieren sich selbst via MQTT Discovery.

### Kamera

**Einstellungen → Geräte & Dienste → Integration hinzufügen → Generic Camera**

| Feld | Wert |
|---|---|
| Still Image URL | `http://<babycam-ip>:5000/api/still` |
| Stream Source | *leer lassen* |
| Framerate | 5 |
| Verify SSL | aus |

Alternativ per REST-API (für Skripte):

```bash
HA_URL="http://192.168.178.131:8123"
TOKEN="dein-ha-token"

FLOW=$(curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "$HA_URL/api/config/config_entries/flow" \
  -d '{"handler":"generic"}' | jq -r '.flow_id')

curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "$HA_URL/api/config/config_entries/flow/$FLOW" \
  -d '{"still_image_url":"http://192.168.178.130:5000/api/still",
       "advanced":{"framerate":5,"verify_ssl":false}}'

curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  "$HA_URL/api/config/config_entries/flow/$FLOW" \
  -d '{"confirmed_ok":true}'
```

> ℹ️ MJPEG-Stream (`/video_feed`) kann **nicht** via go2rtc in HA eingebunden werden. Verwende `/api/still` für periodische Standbilder oder eine Webseiten-Karte mit dem vollen BabyCam-UI.

### Automatisierungs-Beispiele

**Bei Schrei: Push-Benachrichtigung aufs Handy**

```yaml
automation:
  - alias: "BabyCam – Schrei-Alarm"
    trigger:
      - platform: state
        entity_id: binary_sensor.babycam_schreien
        to: "on"
    action:
      - service: notify.mobile_app_mein_handy
        data:
          title: "🚼 BabyCam"
          message: "Baby weint!"
          data:
            push:
              sound: "alert"
```

**Bei Bewegung in der Nacht: Nachtlicht einschalten**

```yaml
automation:
  - alias: "BabyCam – Nachtlicht bei Bewegung"
    trigger:
      - platform: state
        entity_id: binary_sensor.babycam_bewegung
        to: "on"
    condition:
      - condition: state
        entity_id: binary_sensor.babycam_nachtmodus
        state: "on"
    action:
      - service: light.turn_on
        target:
          entity_id: light.nachtlicht
      - delay: "00:05:00"
      - service: light.turn_off
        target:
          entity_id: light.nachtlicht
```

**Lautstärke-Überwachung mit Schwellwert**

```yaml
automation:
  - alias: "BabyCam – Lautstärke-Warnung"
    trigger:
      - platform: numeric_state
        entity_id: sensor.babycam_lautstarke
        above: 0.15
    action:
      - service: persistent_notification.create
        data:
          title: "🔊 BabyCam"
          message: "Lautstärke: {{ states('sensor.babycam_lautstarke') }}"
```

**Kamera-Snapshot bei Ereignis speichern**

```yaml
automation:
  - alias: "BabyCam – Snapshot bei Schrei"
    trigger:
      - platform: state
        entity_id: binary_sensor.babycam_schreien
        to: "on"
    action:
      - service: camera.snapshot
        target:
          entity_id: camera.babycam
        data:
          filename: "/config/www/babycam_schrei.jpg"
```

---

## Telegram-Benachrichtigungen

BabyCam kann Snapshots direkt per Telegram senden — ohne Home Assistant.

1. **Neuen Bot erstellen:** [@BotFather](https://t.me/BotFather) → `/newbot`
2. **Bot-Token** im Web-UI unter ⚙️ Alarm → Telegram eingeben
3. Bot in Telegram öffnen und `/start` senden
4. **🔍 Chat-ID automatisch erkennen** klicken
5. **💾 Speichern** + **📱 Test**

Benachrichtigungen werden bei Bewegung, Schrei und Geräusch gesendet — mit Snapshot-Foto und Cooldown (kein Spam).

---

## API-Referenz

| Endpoint | Methode | Beschreibung |
|---|---|---|
| `/` | GET | Web-Dashboard (volles UI) |
| `/video_feed` | GET | MJPEG Live-Video-Stream |
| `/api/still` | GET | JPEG-Standbild (für HA Generic Camera) |
| `/api/status` | GET | Sensor-Daten: Bewegung, Lautstärke, FPS, Nachtmodus, Uptime |
| `/api/config` | GET/POST | Konfiguration lesen/schreiben (JSON) |
| `/api/debug` | GET | Debug-Status: Info + Ereignis-Log (200 Einträge) |
| `/api/history` | GET | Bewegungs- und Sound-Historie |
| `/api/snapshots` | GET | Liste aller Snapshots mit Zeitstempel |
| `/api/snapshot/<file>` | GET | Einzelnes Snapshot-Bild |
| `/api/audio/latest` | GET | Letzter Audio-Chunk als WAV |
| `/api/camera/preview` | POST | Kamera-Einstellungen live setzen (ohne Speichern) |
| `/api/toggle/audio` | POST | Audio-Stream ein/aus |
| `/api/toggle/video` | POST | Video-Stream ein/aus |
| `/api/telegram/test` | POST | Telegram-Verbindung testen |
| `/api/telegram/discover` | POST | Chat-ID automatisch erkennen |

`/api/debug` Beispiel-Response:

```json
{
  "info": {
    "audio_device": "plughw:1,0",
    "audio_enabled": true,
    "has_video_frame": true,
    "sound_level": 0.0027,
    "cry_detected": false,
    "mqtt_connected": true,
    "mqtt_broker": "192.168.178.131",
    "client_id": "babycam_abc123"
  },
  "log": [
    "[15:03:23] 🎤 Audio-Thread startet: plughw:1,0 @ 16000Hz",
    "[15:03:24] ✅ arecord läuft (PID 17)",
    "[15:05:00] 📡 MQTT verbunden mit 192.168.178.131:1883"
  ]
}
```

---

## Fehlerbehebung

### Kein Video / Kamera nicht erkannt

```bash
# Kamera prüfen
ls /dev/video*
v4l2-ctl --device=/dev/video0 --list-formats

# Docker: device-Mount prüfen
docker inspect babycam | grep -A 5 Devices
# Pi Zero: muss "Devices" zeigen, nicht "Binds"!
```

### Kein Audio / Mikrofon nicht gefunden

```bash
# Mikrofon-Liste
arecord -l
# → Card-Nummer merken

# In der config.json oder via Web-UI anpassen:
# "audio_device": "plughw:X,0"

# Container neustarten
docker compose restart
```

### MQTT-Sensoren erscheinen nicht in Home Assistant

```bash
# MQTT-Verbindung prüfen
curl -s http://<babycam-ip>:5000/api/debug | jq .info.mqtt_connected
# → true = verbunden

# Broker-Erreichbarkeit testen
docker exec babycam python3 -c "
import socket; s=socket.socket(); s.settimeout(3)
s.connect(('192.168.178.131', 1883)); print('OK')
"

# Discovery-Topics prüfen (auf dem HA-Pi):
mosquitto_sub -t "homeassistant/+/babycam_pi/#" -v
```

### FPS-Anzeige ändert sich nicht

Das ist normal! Der FPS-Regler setzt die **Ziel-FPS**. Die tatsächliche FPS (`fps_actual` im Dashboard) ist durch die CPU begrenzt:

| Plattform | Max. FPS |
|---|---|
| Pi 4B | ~15 FPS |
| Pi Zero 2 W | ~5 FPS |

Ziel-FPS **unter** dem Limit wirkt sofort (z.B. FPS=3 → fps_actual≈3.8). Ziel-FPS **über** dem Limit bringt nichts (z.B. FPS=30 → fps_actual≈5).

### Container startet nicht / stürzt ab

```bash
# Logs prüfen
docker logs babycam --tail 50

# Häufige Ursachen:
# - /dev/video0 existiert nicht → docker-compose.pi-one.yml verwenden
# - audio_device falsch → arecord -l prüfen, config.json anpassen
# - MQTT_BROKER nicht erreichbar → IP und Firewall prüfen
```

### Alte Webseite im Browser (Cache)

Nach Updates **hart neuladen**: Strg+Shift+R (Windows/Linux) oder Cmd+Shift+R (Mac). BabyCam setzt `Cache-Control: no-cache`-Header, aber manche Browser ignorieren das.

---

## Update

```bash
cd ~/babycam
git pull
docker build -t babycam:latest .
docker compose down && docker compose up -d
# Pi Zero:
# docker compose -f docker-compose.pi-zero.yml down && docker compose -f docker-compose.pi-zero.yml up -d
```

> 💡 Konfiguration in `config.json` wird durch Updates **nicht** überschrieben — die Datei ist via Volume-Mount persistent.

---

## Backup & Export

```bash
# Docker-Image exportieren
docker save babycam:latest -o babycam.tar

# Auf anderem System importieren
docker load -i babycam.tar

# Komplettes Setup sichern (ohne Snapshots)
tar -czf babycam-backup-$(date +%Y%m%d).tar.gz \
  babycam/ \
  --exclude='babycam/snapshots' \
  --exclude='babycam/__pycache__'
```

---

## Projektstruktur

```
babycam/
├── app.py                          # Hauptanwendung (Flask + OpenCV + MQTT)
├── templates/
│   └── dashboard.html              # Web-Dashboard (Single Page, Dark Mode)
├── static/                         # Statische Assets
├── Dockerfile                      # ARM64 Docker-Image
├── docker-compose.yml              # Standard (Pi 4B mit Kamera)
├── docker-compose.pi-zero.yml      # Pi Zero (devices statt volumes)
├── docker-compose.pi-one.yml       # Pi 4B ohne Kamera (Backup-Instanz)
├── requirements.txt                # Python-Abhängigkeiten
├── config.json                     # Persistente Konfiguration
├── snapshots/                      # Automatische Snapshots (nicht in Git)
├── README.md                       # Diese Datei
└── PI-ZERO-SETUP.md                # Detaillierte Pi-Zero-Anleitung
```

## Technischer Stack

| Komponente | Technologie |
|---|---|
| **Webserver** | Flask (Python 3.13) |
| **Video** | OpenCV (cv2), MJPEG, v4l2-ctl |
| **Audio** | ALSA (`arecord`), NumPy FFT/RMS |
| **Motion Detection** | Frame-Differencing mit Gauß-Filter |
| **MQTT** | paho-mqtt (MQTT v5, Auto-Discovery) |
| **Telegram** | Bot API (HTTP, async Queue) |
| **Frontend** | Vanilla JS, Web Audio API, Dark Mode CSS |
| **Container** | Docker, ARM64, piwheels |

---

## Lizenz

MIT — siehe [LICENSE](LICENSE)

---

*Made with ❤️ for parents who want privacy.*
