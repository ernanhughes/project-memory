# Session 040 — lookup latency

date: 2024-08-05
participants: j.lindqvist, a.novak

J. proposes adding Redis as a lookup cache in front of the event store
to cut read latency for hot keys. No measurements yet; A. asks for
evidence that reads are actually the bottleneck before adding a new
moving part.
