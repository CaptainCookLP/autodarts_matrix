"""Expose AutoDarts round updates via a simple websocket bridge."""

import json
import os
import ssl
import threading
import logging

import certifi
import websocket
import requests
from flask import Flask, jsonify
from flask_socketio import SocketIO

from autodarts_keycloak_client import AutodartsKeycloakClient

AUTODARTS_WEBSOCKET_URL = "wss://api.autodarts.io/ms/v0/subscribe"
SETTINGS_FILE = "/home/pi/rgbserver/settings.json"
WEBSERVER_URL = os.getenv("WEBSERVER_URL", "http://localhost:5000")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
socketio = SocketIO(app, async_mode="threading")

latest_round = {}


def get_env(name: str) -> str:
    """Return the value of an environment variable or raise ``RuntimeError``."""

    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def load_settings() -> dict:
    """Load settings from ``SETTINGS_FILE``."""

    if not os.path.exists(SETTINGS_FILE):
        return {}
    with open(SETTINGS_FILE, "r") as fh:
        return json.load(fh)


def get_setting(name: str) -> str:
    """Return AutoDarts credential ``name`` from env or settings file."""

    env = os.getenv(name)
    if env:
        return env

    mapping = {
        "AUTODARTS_USERNAME": "autodarts_username",
        "AUTODARTS_PASSWORD": "autodarts_password",
        "AUTODARTS_CLIENT_ID": "autodarts_client_id",
        "AUTODARTS_CLIENT_SECRET": "autodarts_client_secret",
        "AUTODARTS_BOARD_ID": "autodarts_board_id",
    }
    settings = load_settings()
    key = mapping.get(name)
    value = settings.get(key) if settings else None
    if not value:
        raise RuntimeError(f"Missing setting: {name}")
    return value


def run_autodarts_ws() -> None:
    """Listen to the AutoDarts websocket and emit round events via SocketIO."""

    os.environ["SSL_CERT_FILE"] = certifi.where()
    kc = AutodartsKeycloakClient(
        username=get_setting("AUTODARTS_USERNAME"),
        password=get_setting("AUTODARTS_PASSWORD"),
        client_id=get_setting("AUTODARTS_CLIENT_ID"),
        client_secret=get_setting("AUTODARTS_CLIENT_SECRET"),
    )
    kc.start()
    board_id = get_setting("AUTODARTS_BOARD_ID")
    logger.info("Connecting to AutoDarts websocket for board %s", board_id)

    def on_open(ws):
        subscribe = {
            "channel": "autodarts.boards",
            "type": "subscribe",
            "topic": f"{board_id}.matches",
        }
        ws.send(json.dumps(subscribe))

    def on_message(ws, message):
        global latest_round
        msg = json.loads(message)
        channel = msg.get("channel")
        data = msg.get("data", {})

        if channel == "autodarts.boards":
            if data.get("event") == "start" and "id" in data:
                match_id = data["id"]
                subscribe_match = {
                    "channel": "autodarts.matches",
                    "type": "subscribe",
                    "topic": f"{match_id}.state",
                }
                ws.send(json.dumps(subscribe_match))
        elif channel == "autodarts.matches":
            turns = data.get("turns") or []
            if turns:
                latest_round = turns[0]
                logger.info("Received round update: %s", latest_round)
                socketio.emit("round", latest_round)
                try:
                    requests.post(f"{WEBSERVER_URL}/dart/update", json=latest_round, timeout=2)
                    logger.info("Forwarded round to %s", WEBSERVER_URL)
                except requests.RequestException as exc:
                    logger.error("Forwarding to webserver failed: %s", exc)

    def on_error(ws, error):
        logger.error("WebSocket error: %s", error)

    def on_close(ws, close_status_code, close_msg):
        logger.info("WebSocket closed")

    headers = {"Authorization": f"Bearer {kc.access_token}"}
    ws = websocket.WebSocketApp(
        AUTODARTS_WEBSOCKET_URL,
        header=headers,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    sslopt = {"cert_reqs": ssl.CERT_REQUIRED, "ca_certs": certifi.where()}
    ws.run_forever(sslopt=sslopt)


@app.route("/round")
def get_round():
    """Return the latest round data received from AutoDarts."""

    return jsonify(latest_round)


def main() -> None:
    """Entry point used when running this module as a script."""

    threading.Thread(target=run_autodarts_ws, daemon=True).start()
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    logger.info("Starting round relay on %s:%s", host, port)
    socketio.run(app, host=host, port=port)


if __name__ == "__main__":
    main()

