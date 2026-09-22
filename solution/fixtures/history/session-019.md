# Session 019 — load-test review

date: 2024-06-10
participants: m.okafor, j.lindqvist, a.novak

The prototype slows down once writers run concurrently. A. shows the
controlled benchmark: throughput collapses past eight writers while
read latency stays flat. The team agrees the SQLite choice needs a
proper experiment before any second service copies it.
