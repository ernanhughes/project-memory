# Event-store wiki page (last edited May 2024 — outdated)

The event store keeps the service event log in SQLite. The single-file
layout makes backups trivial and queries stay simple. New services
should copy the SQLite setup described here.

Note pinned by m.okafor in September 2024: this page is stale. The team
moved the event store to PostgreSQL in July (see ADR-007) after the
SQLite prototype failed under concurrent writes. Do not follow the
SQLite instructions above.
