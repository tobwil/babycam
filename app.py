#!/usr/bin/env python3
"""
BabyCam v2 – Baby Monitor mit Bewegungserkennung, Geräuscherkennung,
Web-Konfiguration, Alert-Cooldown, Snapshots & Nachtmodus.
Läuft offline auf Raspberry Pi mit USB-Webcam.
"""

import cv2
import numpy as np
import threading
import time
import subprocess
import json
import os
import urllib.request
import urllib.parse
import socket
from collections import deque
from datetime import datetime
from flask import Flask, Response, render_template, jsonify, request, send_file
import paho.mqtt.client as mqtt

app = Flask(__name__)

# ── Persistente Konfiguration ──────────────────────────────────
CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')
SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), 'snapshots')
os.makedirs(SNAPSHOT_DIR, exist_ok=True)

DEFAULT_CONFIG = {
    "motion_threshold": 12,
    "motion_min_area": 800,
    "sound_threshold": 0.04,
    "cry_freq_low": 300,
    "cry_freq_high": 800,
    "cry_duration": 1.5,
    "noise_alert_enabled": True,       # Allgemeine Geräuscherkennung (nicht nur Schreien)
    "noise_duration": 1.0,             # Sekunden anhaltendes Geräusch für Noise-Alert
    "alert_cooldown_motion": 30,   # Sekunden zwischen Motion-Alerts
    "alert_cooldown_cry": 60,      # Sekunden zwischen Schrei-Alerts
    "motion_duration_min": 8,      # Sekunden anhaltende Bewegung für Snapshot
    "camera_device": 0,
    "frame_width": 640,
    "frame_height": 480,
    "fps": 15,
    # Kamera-Bildsteuerung (OpenCV CAP_PROP_*)
    "camera_auto": True,               # Auto-Modus (ignoriert manuelle Werte)
    "camera_brightness": 128,          # 0-255
    "camera_contrast": 128,            # 0-255
    "camera_saturation": 128,          # 0-255
    "camera_sharpness": 128,           # 0-255
    "camera_gain": 0,                  # 0-100
    "audio_device": "plughw:3,0",
    "audio_rate": 16000,
    "snapshot_quality": 75,
    "night_mode_auto": True,
    "night_brightness_threshold": 40,  # < 40 mittlere Helligkeit = Nacht
    "telegram_bot_token": "",           # Optional: Bot-Token von @BotFather
    "telegram_chat_id": "",             # Optional: Chat-ID für Nachrichten
    "telegram_enabled": False,          # Telegram-Notifications aktiv?
    "video_enabled": True,              # Live-Video-Stream (MJPEG)
    "audio_enabled": True,              # Live-Audio-Stream + Pegelanzeige
}

def load_config():
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        # Fehlende Keys aus Defaults ergänzen
        for k, v in DEFAULT_CONFIG.items():
            if k not in cfg:
                cfg[k] = v
        return cfg
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_CONFIG)

def save_config(cfg):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(cfg, f, indent=2)

config = load_config()

# ── MQTT-Integration (Home Assistant) ────────────────────────────
MQTT_BROKER = os.environ.get("MQTT_BROKER", "host.docker.internal")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
MQTT_CLIENT_ID = f"babycam_{socket.gethostname()}"

mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID, protocol=mqtt.MQTTv5)
mqtt_connected = False

# MQTT Topics
TOPIC_MOTION = "babycam/motion"
TOPIC_CRY = "babycam/cry"
TOPIC_NOISE = "babycam/noise"
TOPIC_SOUND = "babycam/sound_level"
TOPIC_NIGHT = "babycam/night_mode"
TOPIC_BRIGHTNESS = "babycam/brightness"

# MQTT-Status-Tracking (nur bei Änderung publishen)
_mqtt_last_state = {
    "motion": None,
    "cry": None,
    "noise": None,
    "night_mode": None,
}

def _mqtt_publish(topic, payload, retain=False):
    """Publish an MQTT topic, silently ignoring connection errors."""
    try:
        if mqtt_connected:
            mqtt_client.publish(topic, payload, retain=retain)
    except Exception:
        pass

def _mqtt_publish_if_changed(topic, value, key):
    """Publish only if value changed from last published state."""
    if _mqtt_last_state.get(key) != value:
        _mqtt_last_state[key] = value
        _mqtt_publish(topic, "ON" if value else "OFF")

def _mqtt_send_discovery():
    """Send HA MQTT Auto-Discovery configs (retained)."""
    device = {
        "identifiers": ["babycam_pi"],
        "name": "BabyCam",
        "manufacturer": "Hermes",
        "model": "Pi USB Webcam Monitor",
    }

    # Binary sensors
    for entity, name, device_class in [
        ("motion", "Bewegung", "motion"),
        ("cry", "Schreien", "sound"),
        ("noise", "Geräusch", "sound"),
    ]:
        config = {
            "name": name,
            "device_class": device_class,
            "state_topic": f"babycam/{entity}",
            "unique_id": f"babycam_{entity}",
            "device": device,
        }
        _mqtt_publish(f"homeassistant/binary_sensor/babycam_{entity}/config",
                      json.dumps(config), retain=True)

    # Night mode binary sensor
    _mqtt_publish("homeassistant/binary_sensor/babycam_night/config",
                  json.dumps({
                      "name": "Nachtmodus",
                      "device_class": "light",
                      "state_topic": TOPIC_NIGHT,
                      "unique_id": "babycam_night",
                      "device": device,
                  }), retain=True)

    # Sound level sensor
    _mqtt_publish("homeassistant/sensor/babycam_sound/config",
                  json.dumps({
                      "name": "Lautstärke",
                      "state_topic": TOPIC_SOUND,
                      "unit_of_measurement": "RMS",
                      "unique_id": "babycam_sound",
                      "device": device,
                      "expire_after": 10,
                  }), retain=True)

    # Brightness sensor
    _mqtt_publish("homeassistant/sensor/babycam_brightness/config",
                  json.dumps({
                      "name": "Helligkeit",
                      "state_topic": TOPIC_BRIGHTNESS,
                      "unit_of_measurement": "px",
                      "unique_id": "babycam_brightness",
                      "device": device,
                      "expire_after": 30,
                  }), retain=True)

def on_mqtt_connect(client, userdata, flags, reason_code, properties):
    global mqtt_connected
    mqtt_connected = True
    print(f"[MQTT] Verbunden mit {MQTT_BROKER}:{MQTT_PORT} (rc={reason_code})")
    _mqtt_send_discovery()
    # Reset tracking so current state gets published on next cycle
    for k in _mqtt_last_state:
        _mqtt_last_state[k] = None

def on_mqtt_disconnect(client, userdata, flags, reason_code, properties):
    global mqtt_connected
    mqtt_connected = False
    print(f"[MQTT] Getrennt (rc={reason_code}), reconnect...")

mqtt_client.on_connect = on_mqtt_connect
mqtt_client.on_disconnect = on_mqtt_disconnect
mqtt_client.connect_async(MQTT_BROKER, MQTT_PORT, keepalive=60)
mqtt_client.loop_start()

# ── Globaler Zustand (Thread-safe) ─────────────────────────────
lock = threading.Lock()
state = {
    "motion": False,
    "motion_last": None,
    "motion_history": deque(maxlen=200),
    "sound_level": 0.0,
    "cry_detected": False,
    "cry_last": None,
    "noise_detected": False,
    "noise_last": None,
    "sound_history": deque(maxlen=500),
    "fps_actual": 0.0,
    "uptime": datetime.now(),
    "night_mode": False,
    "brightness": 0.0,
    "snapshots": deque(maxlen=100),  # {"time": iso, "reason": "motion"/"cry", "file": "xxx.jpg"}
    "last_motion_alert": 0,
    "last_cry_alert": 0,
    "last_noise_alert": 0,
    "motion_start_time": 0,          # Timestamp wann Bewegung begann
}

# ── Videostream + Motion-Detection-Thread ───────────────────────
frame_lock = threading.Lock()
latest_frame = None
latest_raw_frame = None  # Für Snapshots (ohne Overlay)

def video_thread():
    global latest_frame, latest_raw_frame
    cap = cv2.VideoCapture(config["camera_device"])
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, config["frame_width"])
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config["frame_height"])
    cap.set(cv2.CAP_PROP_FPS, config["fps"])

    prev_gray = None
    fps_times = deque(maxlen=30)
    W, H = config["frame_width"], config["frame_height"]
    last_cam_settings = None  # Track um nur bei Änderung zu setzen

    while True:
        # Config-Neuladen (falls via API geändert)
        fresh_cfg = load_config()
        mot_thresh = fresh_cfg["motion_threshold"]
        mot_area = fresh_cfg["motion_min_area"]

        # ── Kamera-Einstellungen nur bei Änderung anwenden (via v4l2-ctl) ──
        cam_auto = fresh_cfg.get("camera_auto", True)
        cam_key = (
            cam_auto,
            fresh_cfg.get("camera_brightness", 128),
            fresh_cfg.get("camera_contrast", 128),
            fresh_cfg.get("camera_saturation", 128),
            fresh_cfg.get("camera_sharpness", 128),
            fresh_cfg.get("camera_gain", 0),
        )
        if cam_key != last_cam_settings:
            last_cam_settings = cam_key
            dev = fresh_cfg.get("camera_device", 0)
            if not cam_auto:
                subprocess.run(
                    ["v4l2-ctl", "-d", f"/dev/video{dev}", "-c", "auto_exposure=1",
                     "-c", f"brightness={cam_key[1]}",
                     "-c", f"contrast={cam_key[2]}",
                     "-c", f"saturation={cam_key[3]}",
                     "-c", f"sharpness={cam_key[4]}",
                     "-c", f"gain={cam_key[5]}"],
                    capture_output=True, timeout=2
                )
            else:
                # Erst Defaults, dann Auto
                subprocess.run(
                    ["v4l2-ctl", "-d", f"/dev/video{dev}", "-c", "auto_exposure=1",
                     "-c", "brightness=128", "-c", "contrast=128",
                     "-c", "saturation=128", "-c", "sharpness=128", "-c", "gain=0"],
                    capture_output=True, timeout=2
                )
                subprocess.run(
                    ["v4l2-ctl", "-d", f"/dev/video{dev}", "-c", "auto_exposure=3"],
                    capture_output=True, timeout=2
                )

        t0 = time.time()
        ret, frame = cap.read()
        if not ret:
            time.sleep(0.1)
            continue

        raw = frame.copy()
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        # ── Nachtmodus-Erkennung ──
        brightness = float(np.mean(gray))
        night = fresh_cfg["night_mode_auto"] and brightness < fresh_cfg["night_brightness_threshold"]

        with lock:
            state["brightness"] = round(brightness, 1)
            state["night_mode"] = night
            _mqtt_publish_if_changed(TOPIC_NIGHT, night, "night_mode")
            _mqtt_publish(TOPIC_BRIGHTNESS, str(round(brightness, 1)))

        # ── Motion Detection ──
        if prev_gray is not None:
            delta = cv2.absdiff(prev_gray, gray)
            thresh = cv2.threshold(delta, mot_thresh, 255, cv2.THRESH_BINARY)[1]
            thresh = cv2.dilate(thresh, None, iterations=2)
            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            motion_now = False
            for c in contours:
                if cv2.contourArea(c) >= mot_area:
                    motion_now = True
                    x, y, w, h = cv2.boundingRect(c)
                    overlay_color = (0, 255, 255) if night else (0, 255, 0)
                    cv2.rectangle(frame, (x, y), (x + w, y + h), overlay_color, 2)

            with lock:
                was_motion = state["motion"]
                now_ts = time.time()
                state["motion"] = motion_now
                _mqtt_publish_if_changed(TOPIC_MOTION, motion_now, "motion")

                if motion_now:
                    # Bewegung begann gerade erst → Startzeit merken
                    if not was_motion:
                        state["motion_start_time"] = now_ts
                    state["motion_last"] = datetime.now().isoformat()
                    state["motion_history"].append(state["motion_last"])

                    # Snapshot nur bei anhaltender Bewegung (länger als motion_duration_min)
                    motion_dur = now_ts - state["motion_start_time"]
                    if motion_dur >= fresh_cfg["motion_duration_min"]:
                        if now_ts - state["last_motion_alert"] > fresh_cfg["alert_cooldown_motion"]:
                            state["last_motion_alert"] = now_ts
                            save_snapshot(raw, "motion")
                else:
                    # Bewegung gestoppt → Reset
                    state["motion_start_time"] = 0

        prev_gray = gray

        # ── Status-Overlay ──
        with lock:
            mot = "BEWEGUNG!" if state["motion"] else "ruhig"
            cry = "SCHREIEN!" if state["cry_detected"] else "leise"
            night_txt = " | NACHT" if night else ""
            cv2.putText(frame, f"MOTION: {mot} | AUDIO: {cry} | {state['sound_level']:.3f}{night_txt}",
                       (10, H - 15), cv2.FONT_HERSHEY_SIMPLEX,
                       0.5, (0, 255, 255) if night else (255, 255, 255), 1, cv2.LINE_AA)

        # ── FPS ──
        fps_times.append(time.time())
        if len(fps_times) >= 2:
            state["fps_actual"] = (len(fps_times) - 1) / (fps_times[-1] - fps_times[0])

        # ── JPEG-kodieren ──
        with frame_lock:
            if fresh_cfg.get("video_enabled", True):
                jpeg_q = 50 if night else 70
                _, jpeg = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, jpeg_q])
                latest_frame = jpeg.tobytes()
            else:
                # Video deaktiviert → schwarzes Platzhalterbild
                if latest_frame is None:
                    black = np.zeros((H, W, 3), dtype=np.uint8)
                    _, jpeg = cv2.imencode('.jpg', black)
                    latest_frame = jpeg.tobytes()
            latest_raw_frame = raw  # für Snapshots ohne Overlay

        elapsed = time.time() - t0
        time.sleep(max(0, 1 / config["fps"] - elapsed))


def save_snapshot(frame, reason):
    """Speichert einen Snapshot bei Alert."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{reason}_{ts}.jpg"
    filepath = os.path.join(SNAPSHOT_DIR, filename)

    # Nachtmodus: Helligkeit boosten
    if config["night_mode_auto"]:
        avg = np.mean(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
        if avg < config["night_brightness_threshold"]:
            frame = cv2.convertScaleAbs(frame, alpha=1.5, beta=20)

    cv2.imwrite(filepath, frame, [cv2.IMWRITE_JPEG_QUALITY, config["snapshot_quality"]])
    state["snapshots"].append({
        "time": datetime.now().isoformat(),
        "reason": reason,
        "file": filename,
    })
    # Alte Snapshots löschen (max 100)
    while len(state["snapshots"]) > 100:
        old = state["snapshots"].popleft()
        old_path = os.path.join(SNAPSHOT_DIR, old["file"])
        if os.path.exists(old_path):
            os.remove(old_path)

    # Telegram-Notification senden
    send_telegram_alert(reason, filepath)


# ── Telegram-Integration ────────────────────────────────────────
telegram_queue = deque()
telegram_lock = threading.Lock()

def send_telegram_alert(reason, snapshot_path=None):
    """Sendet Alert via Telegram Bot API (async, non-blocking)."""
    cfg = load_config()
    if not cfg.get("telegram_enabled") or not cfg.get("telegram_bot_token") or not cfg.get("telegram_chat_id"):
        return
    with telegram_lock:
        telegram_queue.append((reason, snapshot_path, time.time()))

def telegram_worker():
    """Hintergrund-Thread: Versendet queued Telegram-Nachrichten."""
    while True:
        try:
            with telegram_lock:
                if not telegram_queue:
                    time.sleep(1)
                    continue
                reason, snapshot_path, ts = telegram_queue.popleft()

            cfg = load_config()
            token = cfg.get("telegram_bot_token", "")
            chat_id = cfg.get("telegram_chat_id", "")

            if not token or not chat_id:
                continue

            # Text
            emoji = {"motion": "👣", "cry": "🔊", "noise": "📢"}.get(reason, "📢")
            label = {"motion": "Bewegung erkannt!", "cry": "Baby schreit!", "noise": "Geräusch erkannt!"}.get(reason, "Alert!")
            t = datetime.now().strftime("%H:%M:%S")
            text = f"{emoji} *BabyCam Alert* – {t}\n{label}"

            # Nachricht senden
            url = f"https://api.telegram.org/bot{token}/sendMessage"
            data = urllib.parse.urlencode({
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown",
            }).encode()
            urllib.request.urlopen(url, data=data, timeout=10)

            # Snapshot als Foto mitschicken
            if snapshot_path and os.path.exists(snapshot_path):
                url2 = f"https://api.telegram.org/bot{token}/sendPhoto"
                import http.client
                import mimetypes
                boundary = "----BabyCamBoundary"
                with open(snapshot_path, "rb") as f:
                    img_data = f.read()
                body = (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="photo"; filename="snapshot.jpg"\r\n'
                    f"Content-Type: image/jpeg\r\n\r\n"
                ).encode() + img_data + f"\r\n--{boundary}--\r\n".encode()
                req = urllib.request.Request(url2, data=body)
                req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
                urllib.request.urlopen(req, timeout=15)

        except Exception as e:
            print(f"[Telegram] Fehler: {e}")
            time.sleep(5)


# ── Audio-Thread ────────────────────────────────────────────────
audio_buffer = deque(maxlen=10)  # Letzte ~640ms Audio für Web-Stream
audio_buffer_lock = threading.Lock()

def audio_thread():
    """Liest via arecord und analysiert Pegel + Frequenz."""
    proc = subprocess.Popen(
        ["arecord", "-D", config["audio_device"], "-f", "S16_LE",
         "-r", str(config["audio_rate"]), "-c", "1", "-t", "raw"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
    )
    cry_counter = 0
    noise_counter = 0
    chunk_size = 4096  # Größere Chunks = weniger CPU-Last
    last_mqtt_sound = 0  # Throttle MQTT sound publish

    while True:
        try:
            fresh_cfg = load_config()
            
            # Blocking read — aber mit größerem Chunk
            data = proc.stdout.read(chunk_size)
            if len(data) < chunk_size:
                continue

            # Audio-Buffer für Live-Stream (nur wenn aktiviert)
            if fresh_cfg.get("audio_enabled", True):
                with audio_buffer_lock:
                    audio_buffer.append(data)
            samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
            rms = np.sqrt(np.mean(samples**2)) / 32768.0

            # Frequenz via Nulldurchgänge
            positives = samples > 0
            zero_crossings = np.sum(positives[:-1] != positives[1:])
            freq = zero_crossings * fresh_cfg["audio_rate"] / (2 * len(samples)) if len(samples) > 1 else 0

            is_cry_freq = fresh_cfg["cry_freq_low"] <= freq <= fresh_cfg["cry_freq_high"]
            is_loud = rms > fresh_cfg["sound_threshold"]

            # Schrei-Erkennung (Frequenz-basiert)
            if is_cry_freq and is_loud:
                cry_counter += 1
            else:
                cry_counter = max(0, cry_counter - 1)

            # Allgemeine Geräuscherkennung (nur Lautstärke, keine Frequenz)
            if fresh_cfg["noise_alert_enabled"]:
                if is_loud:
                    noise_counter += 1
                else:
                    noise_counter = max(0, noise_counter - 1)
            else:
                noise_counter = 0

            cry_needed = int(fresh_cfg["cry_duration"] * fresh_cfg["audio_rate"] / 1024)
            noise_needed = int(fresh_cfg["noise_duration"] * fresh_cfg["audio_rate"] / 1024)
            is_crying = cry_counter >= cry_needed
            is_noise = noise_counter >= noise_needed

            with lock:
                now_ts = time.time()
                state["sound_level"] = round(float(rms), 4)
                state["cry_detected"] = is_crying
                state["noise_detected"] = is_noise
                if now_ts - last_mqtt_sound > 1.0:  # Max 1x/Sekunde
                    _mqtt_publish(TOPIC_SOUND, str(round(float(rms), 4)))
                    last_mqtt_sound = now_ts
                _mqtt_publish_if_changed(TOPIC_CRY, is_crying, "cry")
                _mqtt_publish_if_changed(TOPIC_NOISE, is_noise, "noise")
                state["sound_history"].append({
                    "t": time.time(), "rms": round(float(rms), 4),
                    "freq": round(float(freq), 1), "cry": is_crying, "noise": is_noise,
                })
                if is_crying:
                    now_ts = time.time()
                    state["cry_last"] = datetime.now().isoformat()
                    if now_ts - state["last_cry_alert"] > fresh_cfg["alert_cooldown_cry"]:
                        state["last_cry_alert"] = now_ts
                        with frame_lock:
                            if latest_raw_frame is not None:
                                save_snapshot(latest_raw_frame, "cry")
                elif is_noise and not is_crying:  # Nur Noise (kein Schrei) — separater Alert
                    now_ts = time.time()
                    state["noise_last"] = datetime.now().isoformat()
                    if now_ts - state["last_noise_alert"] > fresh_cfg["alert_cooldown_cry"]:
                        state["last_noise_alert"] = now_ts
                        with frame_lock:
                            if latest_raw_frame is not None:
                                save_snapshot(latest_raw_frame, "noise")

        except Exception:
            time.sleep(0.1)


# ── Flask-Routen ────────────────────────────────────────────────

@app.route('/')
def index():
    return render_template('dashboard.html')

@app.route('/video_feed')
def video_feed():
    def generate():
        while True:
            with frame_lock:
                if latest_frame is None:
                    time.sleep(0.1)
                    continue
                frame = latest_frame
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(1 / config["fps"])
    return Response(generate(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/still')
def api_still():
    """Einzelnes JPEG-Standbild für HA Generic Camera."""
    with frame_lock:
        if latest_frame is None:
            return "", 204
        frame = latest_frame
    return Response(frame, mimetype='image/jpeg')

@app.route('/api/status')
def api_status():
    with lock:
        s = {
            "motion": state["motion"],
            "motion_last": state["motion_last"],
            "motion_duration": round(time.time() - state["motion_start_time"], 1) if state["motion"] and state["motion_start_time"] else 0,
            "sound_level": float(state["sound_level"]),
            "cry_detected": state["cry_detected"],
            "cry_last": state["cry_last"],
            "noise_detected": state["noise_detected"],
            "noise_last": state["noise_last"],
            "fps_actual": float(state["fps_actual"]),
            "night_mode": state["night_mode"],
            "brightness": float(state["brightness"]),
            "uptime": str(datetime.now() - state["uptime"]).split(".")[0],
            "snapshot_count": len(state["snapshots"]),
        }
    return jsonify(s)

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    if request.method == 'POST':
        data = request.get_json()
        if data:
            global config
            for k, v in data.items():
                if k in DEFAULT_CONFIG:
                    config[k] = v
            save_config(config)
        return jsonify({"ok": True})
    return jsonify(config)

@app.route('/api/history')
def api_history():
    with lock:
        sound = []
        for entry in list(state["sound_history"])[-50:]:
            sound.append({
                "t": float(entry["t"]),
                "rms": float(entry["rms"]),
                "freq": float(entry["freq"]),
                "cry": bool(entry["cry"]),
                "noise": bool(entry.get("noise", False)),
            })
        return jsonify({
            "motion": list(state["motion_history"])[-30:],
            "sound": sound,
        })

@app.route('/api/snapshots')
def api_snapshots():
    with lock:
        return jsonify(list(state["snapshots"]))

@app.route('/api/snapshot/<filename>')
def api_snapshot_image(filename):
    # Sicherheitscheck: nur .jpg im Snapshot-Verzeichnis
    if '..' in filename or not filename.endswith('.jpg'):
        return "Nope", 403
    path = os.path.join(SNAPSHOT_DIR, filename)
    if os.path.exists(path):
        return send_file(path, mimetype='image/jpeg')
    return "Not found", 404

@app.route('/api/snapshots/clear', methods=['POST'])
def api_snapshots_clear():
    with lock:
        for s in state["snapshots"]:
            p = os.path.join(SNAPSHOT_DIR, s["file"])
            if os.path.exists(p):
                os.remove(p)
        state["snapshots"].clear()
    return jsonify({"ok": True})

@app.route('/api/telegram/test', methods=['POST'])
def api_telegram_test():
    """Testet die Telegram-Verbindung mit einer Test-Nachricht."""
    cfg = load_config()
    token = cfg.get("telegram_bot_token", "")
    chat_id = cfg.get("telegram_chat_id", "")
    if not token or not chat_id:
        return jsonify({"ok": False, "error": "Token oder Chat-ID nicht konfiguriert"}), 400

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": "✅ *BabyCam Test*\nDie Telegram-Integration funktioniert!",
            "parse_mode": "Markdown",
        }).encode()
        resp = urllib.request.urlopen(url, data=data, timeout=10)
        result = json.loads(resp.read())
        return jsonify({"ok": result.get("ok", False), "detail": result})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500



# ── Kamera-Live-Preview (ohne Config zu speichern) ──────────────

@app.route('/api/audio/latest')
def api_audio_latest():
    """Liefert die letzten ~2s Audio als WAV-Datei für Live-Stream."""
    with audio_buffer_lock:
        chunks = list(audio_buffer)
    if not chunks:
        return "", 204

    # Nur die letzten ~400ms für geringe Latenz
    chunks = chunks[-6:]
    raw = b''.join(chunks)
    data_size = len(raw)
    rate = config["audio_rate"]

    # WAV-Header: 16-bit Mono PCM
    import struct
    header = struct.pack('<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + data_size, b'WAVE',
        b'fmt ', 16, 1, 1, rate, rate * 2, 2, 16,
        b'data', data_size)

    return Response(header + raw, mimetype='audio/wav')


@app.route('/api/camera/preview', methods=['POST'])
def api_camera_preview():
    """Setzt Kamera-Werte live via v4l2-ctl, speichert NICHT in config.json."""
    data = request.get_json(silent=True) or {}
    dev = load_config().get("camera_device", 0)
    args = ["v4l2-ctl", "-d", f"/dev/video{dev}"]

    auto = data.get("camera_auto", True)
    if not auto:
        args += ["-c", "auto_exposure=1"]
        for key in ["camera_brightness", "camera_contrast", "camera_saturation",
                     "camera_sharpness", "camera_gain"]:
            if key in data:
                v4l2_name = key.replace("camera_", "")
                args += ["-c", f"{v4l2_name}={int(data[key])}"]
    else:
        # Bei Auto erst alle Werte auf Default setzen, dann Auto aktivieren
        args += ["-c", "auto_exposure=1",
                 "-c", "brightness=128", "-c", "contrast=128",
                 "-c", "saturation=128", "-c", "sharpness=128", "-c", "gain=0"]
        subprocess.run(args, capture_output=True, timeout=2)
        args = ["v4l2-ctl", "-d", f"/dev/video{dev}", "-c", "auto_exposure=3"]

    try:
        subprocess.run(args, capture_output=True, timeout=2)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/api/telegram/discover', methods=['POST'])
def api_telegram_discover():
    """Findet die Chat-ID automatisch via getUpdates."""
    data = request.get_json(silent=True) or {}
    token = data.get("token", "") or load_config().get("telegram_bot_token", "")
    if not token:
        return jsonify({"ok": False, "error": "Kein Bot-Token. Bitte Token eingeben und speichern."}), 400

    try:
        # Wenn Token via Request kam → in Config speichern
        if data.get("token"):
            cfg = load_config()
            cfg["telegram_bot_token"] = token
            save_config(cfg)

        url = f"https://api.telegram.org/bot{token}/getUpdates"
        resp = urllib.request.urlopen(url, timeout=10)
        data = json.loads(resp.read())
        if data.get("ok") and data.get("result"):
            # Neueste Chat-ID aus den Updates
            latest = data["result"][-1]
            chat_id = str(latest.get("message", {}).get("chat", {}).get("id", ""))
            username = latest.get("message", {}).get("chat", {}).get("username", "")
            first_name = latest.get("message", {}).get("chat", {}).get("first_name", "")
            if chat_id:
                # Automatisch in Config speichern + aktivieren
                cfg["telegram_chat_id"] = chat_id
                cfg["telegram_enabled"] = True
                save_config(cfg)
                return jsonify({
                    "ok": True,
                    "chat_id": chat_id,
                    "name": first_name or username or chat_id,
                })
        return jsonify({"ok": False, "error": "Noch keine Nachricht an den Bot. Bitte sende /start im Telegram-Chat."})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ── Start ───────────────────────────────────────────────────────

if __name__ == '__main__':
    print("🚼 BabyCam v2 startet...")
    print(f"   Kamera: /dev/video{config['camera_device']} ({config['frame_width']}x{config['frame_height']} @ {config['fps']}fps)")
    print(f"   Mikrofon: {config['audio_device']} ({config['audio_rate']}Hz)")
    print(f"   Konfiguration: {CONFIG_FILE}")
    print(f"   Snapshots: {SNAPSHOT_DIR}")
    print(f"   Webinterface: http://0.0.0.0:5000")

    vt = threading.Thread(target=video_thread, daemon=True)
    vt.start()

    at = threading.Thread(target=audio_thread, daemon=True)
    at.start()

    tw = threading.Thread(target=telegram_worker, daemon=True)
    tw.start()

    app.run(host='0.0.0.0', port=5000, threaded=True)
