# Experiment evt-202 — SQLite contention under concurrent writes

date: 2024-06-18
owner: a.novak

Method: 1, 4, 8, 16 concurrent writers against the prototype event log.
Result: write throughput falls 62% at 8 writers and 84% at 16 writers;
median write latency rises from 3ms to 210ms. Reads unaffected.
Conclusion: concurrent-write contention makes SQLite unsuitable for the
shared event-store workload.
