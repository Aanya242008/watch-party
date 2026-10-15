# WatchParty

Watch YouTube videos together with friends: synced playback, live chat, a shared queue, polls and an optional video call. Built with FastAPI and Socket.IO.

## Features

- **Synced playback:** play, pause and seek stay in sync for everyone in the room. Late joiners catch up automatically.
- **Live streams:** YouTube live links work (play and pause sync; there is no timeline to seek).
- **Host controls:** the first person in a room is the host and controls the player. The host can let everyone control it.
- **Video queue:** anyone can add videos; the next one plays automatically when the current one ends.
- **Chat, emoji reactions and a poll:** one vote per person, and you can change your vote.
- **Video call:** up to 6 people using WebRTC (camera and mic need `localhost` or `https`).
- **Invite links:** every visit to the bare URL creates a new random room.

## Run it locally

Requires Python 3.9 or newer.

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS / Linux
pip install -r requirements.txt
python main.py
```

Open http://127.0.0.1:8000, click **Copy invite link**, and open the link in a second tab to try it.

## Deploy

The repo includes a `Procfile` and `render.yaml` for Render, Railway and similar hosts. The start command is:

```bash
uvicorn main:app --host 0.0.0.0 --port $PORT
```

Notes:

- Run a **single worker**. Room state lives in memory, so it resets when the server restarts.
- Camera and mic need `https`, which hosting platforms provide.
- Video calls use a public STUN server only. Some strict networks would need a TURN server.

## Project structure

```
main.py            # server, Socket.IO events and the page (HTML, CSS, JS)
requirements.txt   # Python dependencies
Procfile           # start command for Heroku-style hosts
render.yaml        # Render deployment config
```

## Tech

FastAPI, python-socketio, the YouTube IFrame API and WebRTC.