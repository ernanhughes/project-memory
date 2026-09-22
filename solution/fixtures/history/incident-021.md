# Incident evt-203 — write stalls in the SQLite prototype

date: 2024-06-25
severity: high

During the June load window, event ingestion stalled for 40 minutes.
Root cause: write contention on the SQLite event log under concurrent
writers; the writer queue backed up and ingestion timed out. Mitigation:
drain the queue and throttle writers. Follow-up: select a store that
handles concurrent writes before the next service ships.
