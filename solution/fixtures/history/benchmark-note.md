# Benchmark evt-204 — PostgreSQL candidate for the event store

date: 2024-07-02
owner: a.novak

Same write workload against PostgreSQL 15: throughput holds flat to 32
writers, p99 write latency 11ms. Operational cost is higher than SQLite
(single container, managed backups), but the concurrency behaviour is
decisive for a shared write-heavy service.
