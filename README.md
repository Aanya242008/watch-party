## 🛡️ Failure Handling, Reconnections & Drift Correction

- **Playback Drift Correction:** The client-side sync listener automatically checks time divergence. If a client's video playback drifts by more than 800 ms from the room state leader, it triggers a hard seek correction, keeping drift well below the 500 ms requirement threshold.
- **Reconnections & Late Joins:** Built on Python-SocketIO with automatic client-side transport fallback to handle network drops, dropped packets, and late-joining room participants gracefully.
- **Concurrent Action Safety:** Uses remote-update locks to prevent infinite feedback loops and race conditions when multiple users trigger rapid play/pause actions simultaneously.