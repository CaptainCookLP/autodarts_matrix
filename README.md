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

The project relies on the [hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix)
library for driving the display.  A convenience script is provided to
install or update this dependency along with the Python requirements:

```bash
./install.sh
```

## Running the round relay

Credentials for talking to the AutoDarts API are read from
`settings.json`.  They can be edited via the web interface at `/darts`.

Start the websocket relay service with:

```bash
python simple_round_ws.py
```

## Tests

Run the test-suite with `pytest`:

```bash
pytest
```
