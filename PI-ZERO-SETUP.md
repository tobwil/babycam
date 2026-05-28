# BabyCam – Pi Zero 2 W Setup-Anleitung

> Baby-Monitor mit Bewegungserkennung & Schreierkennung — offline, lokal, kein Internet nötig.
> Inkl. Home Assistant Integration per MQTT + Kamera.

## Hardware

- **Raspberry Pi Zero 2 W** (ARM64/aarch64)
- **USB-Webcam mit Mikrofon** (getestet: Logitech C930e)
- microSD-Karte (≥ 8 GB)
- 5V-Netzteil

## Schritt 1: Raspberry Pi OS installieren

1. **Raspberry Pi Imager** herunterladen: https://www.raspberrypi.com/software/
2. Betriebssystem: **Raspberry Pi OS Lite (64-bit)** — headless, kein Desktop
3. In den Imager-Einstellungen (⚙️):
   - Hostname: `pi-zero` (oder `babycam-zero`)
   - SSH aktivieren
   - Benutzer & Passwort setzen
   - WLAN konfigurieren (falls kein Ethernet)
4. SD-Karte schreiben, in den Zero stecken, booten

## Schritt 2: System vorbereiten

```bash
# SSH auf den Zero
ssh pi@pi-zero.local

# System updaten
sudo apt update && sudo apt upgrade -y

# Docker installieren
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
sudo apt install -y docker-compose-plugin

# Audio-Gruppe für Mikrofon-Zugriff
sudo usermod -aG audio $USER

# Neu einloggen damit Gruppen greifen
exit && ssh pi@pi-zero.local
```

## Schritt 3: Webcam prüfen

```bash
# USB-Webcam einstecken
ls /dev/video0          # Sollte existieren
ls /dev/snd             # Sound-Devices

# Mikrofon finden
arecord -l
# → card 1: C930e [Logitech Webcam C930e], device 0: USB Audio [USB Audio]
#   ↑ Am Zero ist die C930e meist Card 1 (nicht Card 3 wie am Pi 4B!)

# Mikrofon-Test:
arecord -D plughw:1,0 -f S16_LE -r 16000 -c 1 -d 2 test.wav
aplay test.wav
```

> ⚠️ **Wichtig:** Die C930e ist am Pi Zero 2 W meist an **Card 1**, nicht Card 3! Mit `arecord -l` prüfen und in `config.json` eintragen.

## Schritt 4: BabyCam deployen

```bash
git clone https://github.com/tobwil/babycam.git
cd babycam
```

### config.json anpassen

```bash
nano config.json
```

Wichtige Änderungen für den Zero:

```jsonc
{
  "audio_device": "plughw:1,0",   // Card-Nummer vom Zero (arecord -l)
  "fps": 5,                        // Zero packt max. ~5 FPS (CPU-Limit)
  "audio_rate": 16000,             // 16000 reicht, spart CPU vs. 48000
  "sound_threshold": 0.01          // Etwas sensibler als Default 0.04
}
```

### MQTT-Broker setzen

In `docker-compose.pi-zero.yml` die IP deines HA-Pis eintragen:

```yaml
environment:
  - MQTT_BROKER=192.168.178.131
  - MQTT_PORT=1883
```

### Bauen & starten

```bash
# Image bauen (2–3 Minuten auf dem Zero)
docker build -t babycam:latest .

# Mit Zero-spezifischem Compose-File starten
docker compose -f docker-compose.pi-zero.yml up -d
```

> ⚠️ **Unbedingt `docker-compose.pi-zero.yml` verwenden!** Das Standard-Compose-File funktioniert auf dem Zero nicht — `/dev/video0` muss als Device-Mount (nicht Volume) eingebunden werden.

## Schritt 5: Testen

```bash
# Status prüfen
docker compose logs -f

# Webinterface öffnen
http://pi-zero.local:5000
# Oder via IP: http://<pi-zero-ip>:5000
```

Du solltest den Live-Videostream und den Geräuschpegel sehen. Unter ⚙️ Alarm / 📷 Kamera kannst du alles einstellen.

## Performance auf dem Pi Zero 2 W

Der Zero hat eine schwächere CPU als der Pi 4B. Hier die realistischen Werte:

| Metrik | Wert |
|---|---|
| **Max. FPS** | ~5 (darüber CPU-gebunden, bringt nichts) |
| **CPU-Auslastung** | ~50% bei 5 FPS, 640×480, 16kHz Audio |
| **RAM** | ~120–180 MB |
| **Build-Zeit** | ~4 Min (Docker, Erst-Build) |
| **Startzeit** | ~10s bis Webinterface erreichbar |

Der FPS-Regler im Web-UI setzt die **Ziel-FPS** — die tatsächliche FPS ist durch die CPU begrenzt:
- **Ziel ≤ 5** → FPS passt sich an (z.B. 3 → ~3.9 FPS)
- **Ziel > 5** → Zero läuft auf Maximum (~5 FPS), höhere Werte bringen nichts

## Home Assistant Integration

### MQTT-Sensoren (automatisch)

Nach dem Start erscheinen **automatisch** via MQTT Auto-Discovery:

- `binary_sensor.babycam_bewegung` — Bewegung
- `binary_sensor.babycam_schreien` — Schreien
- `binary_sensor.babycam_gerausch` — Geräusch
- `binary_sensor.babycam_nachtmodus` — Nachtmodus
- `sensor.babycam_lautstarke` — Lautstärke (RMS)
- `sensor.babycam_helligkeit` — Bildhelligkeit

Keine YAML-Konfiguration nötig.

### Kamera in HA

**Einstellungen → Geräte & Dienste → Integration hinzufügen → Generic Camera**

- Still Image URL: `http://<pi-zero-ip>:5000/api/still`
- Stream Source: **leer lassen**
- Advanced: Framerate 5, Verify SSL aus

Danach unter Einstellungen → Geräte zu „BabyCam Zero" umbenennen.

## Konfiguration via Web-UI

Alle Einstellungen im Web-UI (⚙️ Alarm / 📷 Kamera) — Änderungen wirken sofort, 💾 Speichern persistiert.

Wichtige Zero-spezifische Einstellungen:

| Einstellung | Zero-Empfehlung | Beschreibung |
|---|---|---|
| FPS | 5 | Höher bringt nichts (CPU-Limit) |
| Audio-Qualität | 16000 Hz | Spart CPU |
| Geräusch-Schwelle | 0.01–0.02 | Etwas sensibler (kleiner Raum) |
| Bewegungs-Empfindlichkeit | 12 | Default passt |

## Fehlerbehebung

### Kein Video / Kamera nicht gefunden

```bash
# Kamera existiert?
ls /dev/video*

# Formate prüfen
v4l2-ctl --device=/dev/video0 --list-formats

# Container-Logs
docker logs babycam 2>&1 | grep -i "video\|kamera"

# Device-Mount prüfen (muss "Devices" zeigen, nicht "Binds")
docker inspect babycam | grep -A 5 Devices
```

### Kein Audio / arecord beendet sich sofort

```bash
# Mikrofon-Card finden
arecord -l

# Im Container-Log prüfen:
docker logs babycam 2>&1 | grep -i "arecord\|audio"

# Häufige Ursache: falsche Card-Nummer in config.json
# → Web-UI: 🎛️ Audio-Gerät auf plughw:X,0 ändern
# → Container neustarten
```

### MQTT-Sensoren erscheinen nicht in HA

```bash
# MQTT-Verbindung prüfen
curl -s http://<pi-zero-ip>:5000/api/debug | python3 -m json.tool | grep mqtt
# → "mqtt_connected": true

# Erreichbarkeit testen (im Container)
docker exec babycam python3 -c "
import socket; s=socket.socket(); s.settimeout(3)
s.connect(('192.168.178.131', 1883)); print('OK')
"

# Docker Compose prüfen
docker inspect babycam | grep MQTT_BROKER
```

### Docker Build-Fehler („COPY static/ not found")

```bash
# In sehr alten Repo-Versionen fehlt der static-Ordner:
mkdir -p static
docker build -t babycam:latest .
```

### Container startet nicht

```bash
# Vollständige Logs
docker logs babycam --tail 100

# Häufige Ursachen:
# - arecord: Cannot get card index → audio_device in config.json falsch
# - /dev/video0 nicht vorhanden → ohne Kamera docker-compose.pi-one.yml verwenden
# - Permission denied /dev/snd → Benutzer in audio-Gruppe?
```

## Update

```bash
cd ~/babycam
git pull
docker build -t babycam:latest .
docker compose -f docker-compose.pi-zero.yml down
docker compose -f docker-compose.pi-zero.yml up -d
```

Konfiguration in `config.json` bleibt durch Updates erhalten (Volume-Mount).

## Multi-Instanz: Zero + Pi 4B

Ein typisches Setup: Zero 2 W im Kinderzimmer (Kamera + Audio), Pi 4B als Home Assistant mit Backup-Instanz.

Der Pi 4B läuft ohne Kamera (`docker-compose.pi-one.yml`) und sendet Audio-Pegel per MQTT. Fällt der Zero aus, hast du immer noch die Audio-Sensoren in HA.

Siehe [README.md](README.md) für Details zum Multi-Instanz-Setup.
