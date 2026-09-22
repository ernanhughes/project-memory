# Notification service runbook (unrelated distractor)

The notification service stores queued messages in its own embedded
database file. Event delivery is at-least-once; duplicate deliveries
are deduplicated by message id. This service shares no storage with
the event-store service and follows a different backup schedule.
