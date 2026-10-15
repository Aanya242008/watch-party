import argparse
import asyncio
import statistics
import time
import socketio

def pct(sorted_vals, p):
    return sorted_vals[min(len(sorted_vals) - 1, int(round(p / 100 * (len(sorted_vals) - 1))))]

async def main(url, n_clients, rounds):
    room = f"bench-{int(time.time())}"
    n_viewers = n_clients - 1
    sent, arrivals = {}, {}

    host = socketio.AsyncClient()
    viewers = [socketio.AsyncClient() for _ in range(n_viewers)]

    for v in viewers:
        @v.on("sync_media")
        async def on_sync(d):
            arrivals.setdefault(int(d["time"]), []).append(time.perf_counter())

    try:
        await host.connect(url)
    except Exception as e:
        print(f"Connection failed. Make sure 'python main.py' is running in another tab! Error: {e}")
        return

    await host.emit("join_room", {"room": room, "cid": "bench-host"})
    await asyncio.sleep(0.3)
    
    for i, v in enumerate(viewers):
        await v.connect(url)
        await v.emit("join_room", {"room": room, "cid": f"bench-viewer-{i}"})
    await asyncio.sleep(0.5)

    lost = 0
    for r in range(1, rounds + 1):
        sent[r] = time.perf_counter()
        await host.emit("media_state", {"room": room, "action": "play" if r % 2 else "pause", "time": float(r)})
        deadline = time.perf_counter() + 2.0
        while len(arrivals.get(r, [])) < n_viewers and time.perf_counter() < deadline:
            await asyncio.sleep(0.0005)
        lost += n_viewers - len(arrivals.get(r, []))
        await asyncio.sleep(0.02)

    samples = sorted((t - sent[r]) * 1000 for r, ts in arrivals.items() for t in ts)
    for c in [host, *viewers]:
        await c.disconnect()
        
    if not samples:
        print("No samples received.")
        return

    p50, p95, p99 = pct(samples, 50), pct(samples, 95), pct(samples, 99)
    print(f"clients={n_clients} rounds={rounds} deliveries={len(samples)} lost={lost}")
    print(f"min {samples[0]:.1f} ms | mean {statistics.mean(samples):.1f} ms | p50 {p50:.1f} ms | "
          f"p95 {p95:.1f} ms | p99 {p99:.1f} ms | max {samples[-1]:.1f} ms")
    print()
    print("Paste into the README:")
    print("| Clients | Samples | Lost | p50 | p95 | p99 | Max |")
    print("|---|---|---|---|---|---|---|")
    print(f"| {n_clients} | {len(samples)} | {lost} | {p50:.1f} ms | {p95:.1f} ms | {p99:.1f} ms | {samples[-1]:.1f} ms |")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--clients", type=int, default=5)
    ap.add_argument("--rounds", type=int, default=300)
    a = ap.parse_args()
    asyncio.run(main(a.url, a.clients, a.rounds))