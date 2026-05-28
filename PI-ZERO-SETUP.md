# BabyCam – Pi Zero 2 W Setup-Anleitung

> Baby-Monitor mit Bewegungserkennung & Schreierkennung — offline, lokal, kein Internet nötig.
> Inkl. Home Assistant Integration per MQTT + Kamera.

## Hardware

- Raspberry Pi Zero 2 W (oder Pi 4B/3B)
- USB-Webcam mit Mikrofon (getestet: Logitech C930e)
- microSD-Karte (≥ 8 GB)
- 5V-Netzteil

## Schritt 1: Raspberry Pi OS installieren

1. **Raspberry Pi Imager** herunterladen: https://www.raspberrypi.com/software/
2. Betriebssystem: **Raspberry Pi OS Lite (64-bit)** – headless, kein Desktop
3. In den Imager-Einstellungen (⚙️):
   - Hostname: `babycam-zero` (oder `babycam`)
   - SSH aktivieren
   - Benutzer & Passwort setzen
   - WLAN konfigurieren (falls kein Ethernet)
4. SD-Karte schreiben, in den Pi Zero stecken, booten

## Schritt 2: Docker installieren

```bash
# SSH auf den Pi
ssh pi@babycam-zero.local

# Docker installieren
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker pi

# Docker Compose Plugin
sudo apt install -y docker-compose-plugin

# Audio-Gruppe für Mikrofon-Zugriff
sudo usermod -aG audio pi

# Neu einloggen damit Gruppen greifen
exit && ssh pi@babycam-zero.local
```

## Schritt 3: Webcam prüfen

```bash
# USB-Webcam einstecken
ls /dev/video0          # Sollte existieren
ls /dev/snd             # Sound-Devices

# Mikrofon finden
arecord -l
# → card X: C930e [Logitech Webcam C930e], device 0

# Mikrofon-Test:
arecord -D plughw:X,0 -f S16_LE -r 16000 -c 1 -d 2 test.wav
aplay test.wav
```

Falls das Mikrofon **nicht** Card 3 ist: nachher in `config.json` (im Web-UI) `audio_device` anpassen, z.B. `"plughw:2,0"`.

## Schritt 4: BabyCam deployen

```bash
git clone https://github.com/tobwil/babycam.git
cd babycam

# MQTT-Broker-Adresse setzen (HA-Pi IP)
# In docker-compose.yml: MQTT_BROKER=192.168.178.131

# Image bauen (2–3 Minuten)
docker build -t babycam:latest .

# Starten
docker compose up -d
```

**Wichtig:** Erst `docker build`, dann `docker compose up` — das Image liegt nicht auf Docker Hub.

## Schritt 5: Testen

```bash
# Status prüfen
docker compose logs -f

# Browser öffnen
http://babycam-zero.local:5000
# Oder via IP: http://<pi-zero-ip>:5000
```

Du solltest den Live-Videostream und den Geräuschpegel sehen. Unter ⚙️ Alarm / 📷 Kamera kannst du alles einstellen.

## Home Assistant Integration

### MQTT-Sensoren (automatisch)

In `docker-compose.yml` die IP deines HA-Pis eintragen:

```yaml
environment:
  - MQTT_BROKER=192.168.178.131   # ← HA-Pi mit Mosquitto
  - MQTT_PORT=1883
```

Nach dem Start (`docker compose up -d`) erscheinen automatisch in HA:

- `binary_sensor.babycam_babycam_bewegung` — Bewegung
- `binary_sensor.babycam_babycam_schreien` — Schreien
- `binary_sensor.babycam_babycam_gerausch` — Geräusch
- `binary_sensor.babycam_babycam_nachtmodus` — Nachtmodus
- `sensor.babycam_babycam_lautstarke` — Lautstärke (RMS)
- `sensor.babycam_babycam_helligkeit` — Bildhelligkeit

Keine YAML-Konfiguration nötig — MQTT Auto-Discovery.

### Kamera in HA

**Einstellungen → Geräte & Dienste → Integration hinzufügen → Generic Camera**

- Still Image URL: `http://<pi-zero-ip>:5000/api/still`
- Stream Source: **leer lassen**
- Advanced: Framerate 5, Verify SSL aus

Danach unter Einstellungen → Geräte zu „BabyCam Zero" umbenennen.

## Performance auf Pi Zero 2 W

- CPU-Auslastung: ~40–60% (15fps, 640×480)
- RAM: ~120–180 MB
- Stromverbrauch: ~2–3W (inkl. Webcam)
- Startzeit: ~10s bis Webinterface erreichbar

## Konfiguration

Alle Einstellungen im **Web-UI** (⚙️ Alarm / 📷 Kamera) — kein Neustart nötig:

| Einstellung | Default | Beschreibung |
|---|---|---|
| Bewegungs-Empfindlichkeit | 12 | Je niedriger, desto empfindlicher |
| Min. Bewegungsfläche | 800 px² | Ignoriert kleine Bewegungen |
| Geräusch-Schwelle | 0.04 RMS | Lautstärke für Noise-Alert |
| Schrei-Frequenz | 300–800 Hz | Frequenzbereich für Schreien |
| Mindest-Bewegungsdauer | 8s | Snapshots erst nach anhaltender Bewegung |
| Motion-Cooldown | 30s | Mindestabstand zwischen Alerts |

Konfiguration wird in `config.json` gespeichert und überlebt Neustarts.

## Fehlerbehebung

**Kein Video:**
```bash
v4l2-ctl --device=/dev/video0 --list-formats
docker compose restart
```

**Kein Audio:**
```bash
arecord -l                              # Device-Nummer prüfen
# audio_device in config.json anpassen, z.B. "plughw:2,0"
docker compose restart
```

**MQTT-Sensoren erscheinen nicht in HA:**
```bash
# Prüfen ob MQTT verbunden ist
docker logs babycam 2>&1 | grep MQTT
# Sollte zeigen: [MQTT] Verbunden mit 192.168.178.131:1883
```

**Container startet nicht:**
```bash
docker compose logs babycam
# Prüfen: /dev/video0 und /dev/snd werden durchgereicht?
```

**Docker Build-Fehler („COPY static/ static/ not found"):**
```bash
mkdir static    # Ordner fehlt (in älteren Repo-Versionen)
docker build -t babycam:latest .
```

## Update

```bash
cd ~/babycam
git pull
docker build -t babycam:latest .
docker compose down && docker compose up -d
```
