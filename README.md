## 📊 Latency Benchmarking & Performance

To evaluate the real-time performance of the socket-based message relay system, a custom benchmarking script (`bench_latency.py`) was executed to measure one-way delivery delay (host emit $\rightarrow$ server relay $\rightarrow$ viewer receive).

### Test Conditions
- **Environment:** Localhost loopback interface (`127.0.0.1`) running via Uvicorn ASGI server.
- **Concurrency Setup:** 5 concurrent clients (1 host, 4 viewers) across 300 test rounds.

### Performance Results

| Clients | Samples | Lost | p50 | p95 | p99 | Max |
|---|---|---|---|---|---|---|
| 5 | 1200 | 0 | 2.9 ms | 4.5 ms | 5.0 ms | 5.6 ms |

* **Conclusion:** The p95 delivery latency ($4.5\text{ ms}$) is exceptionally fast and well below the target threshold ($\le 250\text{ ms}$).
