# Session 014 — event-store backend discussion

date: 2024-03-04
participants: m.okafor, j.lindqvist

We need somewhere to keep the service event log. M. proposes SQLite:
single file, no operations burden, easy to back up. J. worries about
concurrent writers but agrees to try it for the first prototype.

Agreement: start with SQLite for the prototype (evt-201) and revisit if
write contention shows up under load.
