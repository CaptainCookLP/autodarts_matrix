import os
import json
import threading
import time
import subprocess
from flask import Flask, render_template_string, request, redirect, send_from_directory, jsonify, render_template, flash
from datetime import datetime
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from PIL import Image

app = Flask(__name__)

GIF_FOLDER = "/home/pi/rgbserver/gifs"
PLAYLIST_FILE = "/home/pi/rgbserver/playlist.json"
SETTINGS_FILE = "/home/pi/rgbserver/settings.json"

gif_player_running = False
gif_player_thread = None
gif_player_stop = threading.Event()
display_enabled = True
app.secret_key = "random-secret-key"

current_ssid = "?"
ip_address = "Keine IP"
hotspot_active = False

dart_state = {
    "players": [],    # [{"name":"Fabian","score":501,"sets":0,"legs":0}, ...]
    "current": 0,     # Index des aktuellen Spielers
    "checkout": ""    # z.B. "T20 T19 D8" (kommt später via WebSocket)
}
last_dart_update = 0.0          # monotonic timestamp
pg_autoplay_active = False       # True, wenn Watchdog die PG-GIFs gestartet hat
INACTIVITY_SECS = 5 * 60         # 5 Minuten
dart_mode = False
state_lock = threading.Lock()

# Farben
color_white = graphics.Color(255, 255, 255)
color_green = graphics.Color(0, 255, 0)
color_cyan  = graphics.Color(0, 200, 255)
color_yellow = graphics.Color(255, 255, 0)


# Matrix Setup
def load_settings():
    with open(SETTINGS_FILE, "r") as f:
        return json.load(f)

def save_settings(settings):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)

settings = load_settings()
options = RGBMatrixOptions()
options.rows = settings.get("rows", 64)
options.cols = settings.get("cols", 64)
options.chain_length = settings.get("chain_length", 3)
options.hardware_mapping = settings.get("hardware_mapping", 'regular')
options.gpio_slowdown = settings.get("gpio_slowdown", 4)
options.brightness = 100
#options.pwm_lsb_nanoseconds = 130
#options.pwm_dither_bits = 1
options.limit_refresh_rate_hz = 60

matrix = RGBMatrix(options=options)
canvas = matrix.CreateFrameCanvas()
font = graphics.Font()
font.LoadFont("/home/pi/rpi-rgb-led-matrix/fonts/5x8.bdf")
textColor = graphics.Color(255, 255, 0)
font_dart = graphics.Font()
font_dart.LoadFont("/home/pi/rpi-rgb-led-matrix/fonts/9x18B.bdf")

# WLAN & IP Funktionen
def get_connected_ssid():
    result = subprocess.run(['iwgetid', '-r'], stdout=subprocess.PIPE)
    return result.stdout.decode().strip()

def get_ip():
    result = subprocess.run(['hostname', '-I'], stdout=subprocess.PIPE)
    ip = result.stdout.decode().strip().split(' ')[0]
    return ip if ip else "Keine IP"

def wlan_monitor():
    global ip_address, current_ssid, hotspot_active
    while True:
        ssid = get_connected_ssid()
        if ssid:
            current_ssid = ssid
            ip_address = get_ip()
        else:
            current_ssid = "Hotspot"
            ip_address = "192.168.50.1"
        time.sleep(10)

# Display
def display_loop():
    global display_enabled, canvas, dart_mode
    while True:
        if display_enabled:
            if dart_mode:
                draw_dart_screen()
                canvas = matrix.SwapOnVSync(canvas)
            else:
                canvas.Clear()
                now = datetime.now().strftime("%H:%M:%S")

                if current_ssid != "Hotspot":
                    graphics.DrawText(canvas, font, 2, 20, textColor, f"IP: {ip_address}")
                    graphics.DrawText(canvas, font, 2, 35, textColor, f"SSID: {current_ssid}")
                    graphics.DrawText(canvas, font, 2, 50, textColor, f"Uhrzeit: {now}")
                else:
                    graphics.DrawText(canvas, font, 2, 20, textColor, "Verbinde mit:")
                    graphics.DrawText(canvas, font, 2, 35, textColor, "LEDMatrix-Controller")
                    graphics.DrawText(canvas, font, 2, 45, textColor, f"IP: 192.168.50.1")
                    graphics.DrawText(canvas, font, 2, 50, textColor, f"Uhrzeit: {now}")

                canvas = matrix.SwapOnVSync(canvas)
        time.sleep(1)

def draw_dart_screen():
    """Alle Spieler untereinander: Name links, Score/Sets/Legs rechtsbündig; Checkout zentriert in Zeile 4 wenn <=3 Spieler."""
    with state_lock:
        players = list(dart_state.get("players", []))
        current = int(dart_state.get("current", 0))
        checkout_text = str(dart_state.get("checkout", "") or "")

    canvas.Clear()

    if not players:
        graphics.DrawText(canvas, font_dart, 2, 12, color_white, "Keine Spieler")
        return

    # Layout (dein Spacing)
    y_start = 12
    line_spacing = 16
    padding = 2

    # Matrix-Breite in Pixeln
    max_width = options.cols * options.chain_length

    # Max-Breiten der Zahlenspalten ermitteln
    def text_w(txt, col=color_white):
        # off-screen draw zum Messen
        return graphics.DrawText(canvas, font_dart, 0, -9999, col, str(txt))

    max_score_w = max(text_w(p.get("score", 0)) for p in players)
    max_sets_w  = max(text_w(p.get("sets", 0))  for p in players)
    max_legs_w  = max(text_w(p.get("legs", 0))  for p in players)

    # Spaltenpositionen (von rechts nach links)
    x_legs  = max_width - max_legs_w - padding
    x_sets  = x_legs - max_sets_w - 6
    x_score = x_sets - max_score_w - 6
    x_name  = 2

    # Spielerzeilen zeichnen (Reihenfolge bleibt exakt)
    for idx, p in enumerate(players):
        col   = color_green if idx == current else color_white
        name  = str(p.get("name", "Spieler"))
        score = str(p.get("score", 0))
        sets  = str(p.get("sets", 0))
        legs  = str(p.get("legs", 0))

        y = y_start + idx * line_spacing

        # Name links
        graphics.DrawText(canvas, font_dart, x_name, y, col, name)

        # Zahlen rechtsbündig in ihren Spalten
        sw = text_w(score, col)
        tw = text_w(sets,  col)
        lw = text_w(legs,  col)

        graphics.DrawText(canvas, font_dart, x_score + (max_score_w - sw), y, col, score)
        graphics.DrawText(canvas, font_dart, x_sets  + (max_sets_w  - tw), y, col, sets)
        graphics.DrawText(canvas, font_dart, x_legs  + (max_legs_w  - lw), y, col, legs)

    # Checkout-Anzeige:
    # - nur wenn <= 3 Spieler
    # - in "Zeile 4" (y für idx 3)
    # - zentriert, und nur wenn checkout_text != ""
    n = len(players)
    if 1 <= n <= 3 and checkout_text:
        y_checkout = y_start + 3 * line_spacing  # Position wie Spieler 4
        w_checkout = text_w(checkout_text, color_yellow)
        x_checkout = max(0, (max_width - w_checkout) // 2)
        graphics.DrawText(canvas, font_dart, x_checkout, y_checkout, color_yellow, checkout_text)


# GIF Player
def play_gifs(gif_list):
    global gif_player_running, display_enabled
    gif_player_running = True
    display_enabled = False
    try:
        while not gif_player_stop.is_set():
            for gif_path in gif_list:
                if gif_player_stop.is_set():
                    break
                gif = Image.open(gif_path)
                for frame in range(gif.n_frames):
                    if gif_player_stop.is_set():
                        break
                    gif.seek(frame)
                    matrix.SetImage(gif.convert('RGB'), 0, 0)
                    time.sleep(gif.info.get('duration', 100) / 1000.0)
    finally:
        matrix.Clear()
        gif_player_running = False
        display_enabled = True

# Playlist Helper
def load_playlist():
    if os.path.exists(PLAYLIST_FILE):
        with open(PLAYLIST_FILE, "r") as f:
            return json.load(f)
    return {"order": []}

def save_playlist(data):
    with open(PLAYLIST_FILE, "w") as f:
        json.dump(data, f, indent=4)
        
def start_pg_autoplay():
    """Starte GIF-Loop aus GIF_FOLDER/pg."""
    global gif_player_thread, gif_player_stop, pg_autoplay_active

    pg_path = os.path.join(GIF_FOLDER, "pg")
    if not os.path.isdir(pg_path):
        return False, "Ordner gifs/pg nicht gefunden"

    gif_files = [f for f in os.listdir(pg_path) if f.lower().endswith(".gif")]
    if not gif_files:
        return False, "Keine GIFs in gifs/pg"

    full_paths = [os.path.join(pg_path, f) for f in gif_files]
    full_paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)

    # laufenden Player stoppen
    if gif_player_thread and gif_player_thread.is_alive():
        gif_player_stop.set()
        gif_player_thread.join()

    gif_player_stop.clear()
    gif_player_thread = threading.Thread(target=play_gifs, args=(full_paths,), daemon=True)
    gif_player_thread.start()
    pg_autoplay_active = True
    return True, f"{len(full_paths)} GIFs gestartet"
    
def stop_pg_autoplay_if_running():
    """Stoppt nur das vom Autoplay gestartete PG-GIF-Loop."""
    global gif_player_thread, gif_player_stop, pg_autoplay_active
    if pg_autoplay_active and gif_player_thread and gif_player_thread.is_alive():
        gif_player_stop.set()
        gif_player_thread.join()
    pg_autoplay_active = False


# === WEB ROUTES ===

@app.route("/gifs/<path:filename>")
def gifs_static(filename):
    return send_from_directory(GIF_FOLDER, filename)

@app.route("/")
def index():
    now = datetime.now().strftime("%H:%M:%S")
    return render_template("index.html", ssid=current_ssid, ip=ip_address, time=now)


@app.route("/settings", methods=["GET", "POST"])
def config():
    settings = load_settings()
    if request.method == "POST":
        settings.update({
            "rows": int(request.form.get("rows")),
            "cols": int(request.form.get("cols")),
            "chain_length": int(request.form.get("chain_length")),
            "hardware_mapping": request.form.get("hardware_mapping"),
            "gpio_slowdown": int(request.form.get("gpio_slowdown")),
            "pwm_lsb_nanoseconds": int(request.form.get("pwm_lsb_nanoseconds"))
        })
        save_settings(settings)
        return redirect("/settings")

    return render_template("settings.html", s=settings)


@app.route("/darts", methods=["GET", "POST"])
def darts_settings():
    settings = load_settings()
    if request.method == "POST":
        settings.update({
            "autodarts_username": request.form.get("autodarts_username", ""),
            "autodarts_password": request.form.get("autodarts_password", ""),
            "autodarts_client_id": request.form.get("autodarts_client_id", ""),
            "autodarts_client_secret": request.form.get("autodarts_client_secret", ""),
            "autodarts_board_id": request.form.get("autodarts_board_id", ""),
        })
        save_settings(settings)
        return redirect("/darts")

    return render_template("darts.html", s=settings)

@app.route("/gif")
def gif_list():
    gif_files = [f for f in os.listdir(GIF_FOLDER) if f.lower().endswith(".gif")]
    gif_files.sort(key=lambda x: os.path.getmtime(os.path.join(GIF_FOLDER, x)), reverse=True)

    return render_template("gifs.html", gifs=gif_files, status=("Läuft" if gif_player_running else "Gestoppt"))


@app.route("/gif/start", methods=["POST"])
def gif_start():
    gif = request.form.get("gif")
    gif_path = os.path.join(GIF_FOLDER, gif)

    global gif_player_thread, gif_player_stop
    if gif_player_thread and gif_player_thread.is_alive():
        gif_player_stop.set()
        gif_player_thread.join()

    gif_player_stop.clear()
    gif_player_thread = threading.Thread(target=play_gifs, args=([gif_path],), daemon=True)
    gif_player_thread.start()
    return redirect("/gif")

@app.route("/gif/stop", methods=["POST"])
def gif_stop():
    global gif_player_thread, gif_player_stop
    if gif_player_thread and gif_player_thread.is_alive():
        gif_player_stop.set()
        gif_player_thread.join()
    return redirect("/gif")

@app.route("/playlist")
def playlist_page():
    playlist = load_playlist()
    gifs = sorted([f for f in os.listdir(GIF_FOLDER) if f.lower().endswith(".gif")])
    return render_template("playlist.html", gifs=gifs, playlist=playlist)



@app.route("/save_playlist", methods=["POST"])
def playlist_save():
    save_playlist(request.get_json())
    return jsonify({"status": "saved"})

@app.route("/playlist/start", methods=["POST"])
def playlist_start():
    playlist = load_playlist()
    full_paths = [os.path.join(GIF_FOLDER, gif) for gif in playlist['order']]

    global gif_player_thread, gif_player_stop
    if gif_player_thread and gif_player_thread.is_alive():
        gif_player_stop.set()
        gif_player_thread.join()

    gif_player_stop.clear()
    gif_player_thread = threading.Thread(target=play_gifs, args=(full_paths,), daemon=True)
    gif_player_thread.start()
    return redirect("/playlist")

@app.route("/gif/upload", methods=["POST"])
def gif_upload():
    if 'gif_file' not in request.files:
        flash("Keine Datei ausgewählt.", "danger")
        return redirect("/gif")

    file = request.files['gif_file']

    if file.filename == '':
        flash("Keine Datei ausgewählt.", "danger")
        return redirect("/gif")

    if not file.filename.lower().endswith('.gif'):
        flash("Nur GIF-Dateien erlaubt.", "danger")
        return redirect("/gif")

    save_path = os.path.join(GIF_FOLDER, file.filename)

    # Prüfen ob Datei existiert
    if os.path.exists(save_path):
        # Wenn ja → umbenennen (anhängen _x)
        base, ext = os.path.splitext(file.filename)
        counter = 1
        new_filename = f"{base}_{counter}{ext}"

        while os.path.exists(os.path.join(GIF_FOLDER, new_filename)):
            counter += 1
            new_filename = f"{base}_{counter}{ext}"

        save_path = os.path.join(GIF_FOLDER, new_filename)
        flash(f"Datei existierte bereits. Gespeichert als {new_filename}.", "warning")
    else:
        flash("GIF hochgeladen!", "success")

    file.save(save_path)
    os.chmod(save_path, 0o777)

    return redirect("/gif")

@app.route("/gif/delete", methods=["POST"])
def gif_delete():
    gif = request.form.get("gif")
    gif_path = os.path.join(GIF_FOLDER, gif)

    if os.path.exists(gif_path):
        os.remove(gif_path)
        flash(f"{gif} wurde gelöscht.", "success")
    else:
        flash("Datei existiert nicht.", "danger")

    return redirect("/gif")

@app.route("/dart")
def dart_webtab():
    return render_template("dart.html")


@app.route("/dart/start", methods=["POST"])
def dart_start():
    global dart_mode, last_dart_update
    data = request.get_json(force=True, silent=True) or {}
    players = data.get("players", [])
    current = int(data.get("current", 0))
    checkout = str(data.get("checkout", "") or "")

    if not players:
        return jsonify({"error":"players required"}), 400

    with state_lock:
        dart_state["players"] = players
        dart_state["current"] = max(0, min(current, len(players)-1))
        dart_state["checkout"] = checkout
        dart_mode = True

    last_dart_update = time.monotonic()
    stop_pg_autoplay_if_running()
    return jsonify({"status":"dart mode on"})

@app.route("/dart/update", methods=["POST"])
def dart_update():
    global last_dart_update
    data = request.get_json(force=True, silent=True) or {}
    with state_lock:
        if "players" in data and isinstance(data["players"], list) and data["players"]:
            dart_state["players"] = data["players"]
            dart_state["current"] = min(dart_state["current"], len(dart_state["players"]) - 1)
        if "current" in data:
            players = dart_state.get("players", [])
            if players:
                dart_state["current"] = max(0, min(int(data["current"]), len(players)-1))
        if "checkout" in data:
            dart_state["checkout"] = str(data.get("checkout") or "")

    last_dart_update = time.monotonic()
    stop_pg_autoplay_if_running()
    return jsonify({"status":"updated"})

@app.route("/dart/next", methods=["POST"])
def dart_next():
    with state_lock:
        players = dart_state.get("players", [])
        if players:
            dart_state["current"] = (dart_state["current"] + 1) % len(players)
    return jsonify({"status":"next"})

@app.route("/dart/stop", methods=["POST"])
def dart_stop():
    global dart_mode, pg_autoplay_active
    dart_mode = False  # Darts-Ansicht aus

    # optional: Checkout leeren
    with state_lock:
        dart_state["checkout"] = ""

    # GIFs aus gifs/pg sofort starten
    started, msg = start_pg_autoplay()
    return jsonify({
        "status": "dart mode off",
        "pg_started": started,
        "message": msg
    })


if __name__ == "__main__":
    threading.Thread(target=wlan_monitor, daemon=True).start()
    threading.Thread(target=display_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=5000)
