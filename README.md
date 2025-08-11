# autodarts_matrix

Utilities for relaying AutoDarts match information and displaying data on an
RGB matrix.  The project contains two main entry points:

* `simple_round_ws.py` &ndash; subscribes to the AutoDarts websocket API and
  exposes the latest round as a small Flask/Socket.IO service.
* `webserver.py` &ndash; Raspberry&nbsp;Pi oriented web UI for controlling an RGB LED
  matrix and showing player information or GIF playlists.

## Development

Set up a virtual environment and install the dependencies, including those required for running tests:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the round relay

The websocket relay requires a number of environment variables for authenticating
against AutoDarts:

- `AUTODARTS_USERNAME`
- `AUTODARTS_PASSWORD`
- `AUTODARTS_CLIENT_ID`
- `AUTODARTS_CLIENT_SECRET`
- `AUTODARTS_BOARD_ID`

Start the service with:

```bash
python simple_round_ws.py
```

## Tests

Run the test-suite with `pytest`:

```bash
pytest
```
