# BabyCam – Pi Zero 2 W Setup-Anleitung

> Baby-Monitor mit Bewegungserkennung & Schreierkennung – offline, lokal, kein Internet nötig.

## Hardware

- Raspberry Pi Zero 2 W (oder Pi 4B/3B)
- USB-Webcam mit Mikrofon (getestet: Logitech C930e)
- microSD-Karte (≥ 8 GB)
- 5V-Netzteil

## Schritt 1: Raspberry Pi OS installieren

1. **Raspberry Pi Imager** herunterladen: https://www.raspberrypi.com/software/
2. Betriebssystem: **Raspberry Pi OS Lite (64-bit)** – headless, kein Desktop
3. In den Imager-Einstellungen (⚙️):
   - Hostname: `babycam`
   - SSH aktivieren
   - Benutzer & Passwort setzen
   - WLAN konfigurieren (falls kein Ethernet)
4. SD-Karte schreiben, in den Pi Zero stecken, booten

## Schritt 2: Docker installieren

```bash
# SSH auf den Pi
ssh pi@babycam.local

# Docker installieren (offizielle Methode)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker pi

# Docker Compose Plugin
sudo apt install -y docker-compose-plugin

# Neu einloggen damit Gruppen greifen
exit && ssh pi@babycam.local
```

### Alternative: Docker Rootless (empfohlen für mehr Sicherheit)

```bash
# Rootless Docker Setup
sudo apt install -y uidmap dbus-user-session
dockerd-rootless-setuptool.sh install
systemctl --user enable docker
systemctl --user start docker
sudo loginctl enable-linger pi

# Docker Compose für Rootless
DOCKER_CONFIG=${DOCKER_CONFIG:-$HOME/.docker}
mkdir -p $DOCKER_CONFIG/cli-plugins
curl -SL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-aarch64" \
  -o $DOCKER_CONFIG/cli-plugins/docker-compose
chmod +x $DOCKER_CONFIG/cli-plugins/docker-compose
```

## Schritt 3: BabyCam deployen

```bash
# Webcam einstecken und prüfen
ls /dev/video0    # Sollte existieren
arecord -l        # Mikrofon sollte gelistet sein

# Audio-Gruppe hinzufügen (für Rootless Docker)
sudo usermod -aG audio pi

# Projekt klonen (GitHub) oder per SCP kopieren
git clone https://github.com/<user>/babycam.git
# ODER: Von Pi 4B kopieren:
# scp -r pi@192.168.178.199:~/babycam .

cd babycam

# Docker-Image bauen und starten
docker compose up -d
```

## Schritt 4: Testen

```bash
# Status prüfen
docker compose logs -f

# Browser öffnen
http://babycam.local:5000
# Oder via IP: http://<pi-ip>:5000
```

Du solltest den Live-Videostream, die Bewegungserkennung und den Geräuschpegel sehen.

## Konfiguration

Alle Einstellungen in `app.py` (oben im `# ── Konfiguration`-Block):

| Parameter | Default | Beschreibung |
|-----------|---------|-------------|
| `MOTION_THRESHOLD` | 12 | Empfindlichkeit (0–255, niedriger = sensibler) |
| `MOTION_MIN_AREA` | 800 | Minimale Bewegungsfläche in px² |
| `CRY_FREQ_LOW` | 300 | Untere Schreifrequenz (Hz) |
| `CRY_FREQ_HIGH` | 800 | Obere Schreifrequenz (Hz) |
| `CRY_LOUD_THRESHOLD` | 0.08 | RMS-Lautstärke-Schwelle |
| `CRY_DURATION` | 1.5 | Sekunden anhaltender Schrei für Alert |

Nach Änderungen: `docker compose restart`

## Performance auf Pi Zero 2 W

- CPU-Auslastung: ~40–60% (15fps, 640×480)
- RAM: ~120–180 MB
- Stromverbrauch: ~2–3W (inkl. Webcam)

## Fehlerbehebung

**Kein Video:**
```bash
v4l2-ctl --device=/dev/video0 --list-formats
docker compose restart
```

**Kein Audio:**
```bash
arecord -D plughw:3,0 -d 2 test.wav  # Aufnahme testen
# Device-Nummer in app.py anpassen (AUDIO_DEVICE)
```

**Container startet nicht:**
```bash
docker compose logs babycam
# Prüfen: /dev/video0 und /dev/snd werden durchgereicht?
```
