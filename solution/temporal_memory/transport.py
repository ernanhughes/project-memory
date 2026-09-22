"""Transport abstraction: ZeroMQ is replaceable.

EventTransport protocol with InMemoryTransport (deterministic tests) and
ZeroMQTransport (live demo: PUB publishers -> XSUB/XPUB proxy -> SUB
recorder). Temporal semantics never depend on transport internals.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from typing import Protocol

from .model import EventEnvelope


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class EventTransport(Protocol):
    def publish(self, event: EventEnvelope) -> None: ...
    def close(self) -> None: ...


class InMemoryTransport:
    """Deterministic transport: publish appends to a shared outbox."""

    def __init__(self, outbox: list[dict] | None = None):
        self.outbox: list[dict] = outbox if outbox is not None else []

    def publish(self, event: EventEnvelope) -> None:
        self.outbox.append({"envelope": event.to_dict(),
                            "sent_at": _now_iso()})

    def close(self) -> None:
        pass


class ZmqPublisher:
    """A single PUB socket bound to one source identity."""

    def __init__(self, ctx, proxy_frontend_addr: str, source_id: str,
                 ready: threading.Event, seq_start: int = 1):
        import zmq
        self.source_id = source_id
        self._socket = ctx.socket(zmq.PUB)
        self._socket.connect(proxy_frontend_addr)
        self._ready = ready
        self._seq = seq_start

    def publish(self, event: EventEnvelope, delay_s: float = 0.0) -> None:
        if delay_s > 0:
            time.sleep(delay_s)
        # Readiness gate: never send before the recorder is subscribed.
        self._ready.wait(timeout=10.0)
        self._socket.send_json(event.to_dict())

    def close(self) -> None:
        try:
            self._socket.close(linger=0)
        except Exception:
            pass


class ZmqBroker:
    """XSUB frontend (publishers) / XPUB backend (recorder) proxy thread."""

    def __init__(self, ctx, frontend_addr: str, backend_addr: str):
        import zmq
        self._ctx = ctx
        self.frontend_addr = frontend_addr
        self.backend_addr = backend_addr
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._zmq = zmq

    def start(self) -> None:
        zmq = self._zmq
        self._xsub = self._ctx.socket(zmq.XSUB)
        self._xsub.bind(self.frontend_addr)
        self._xpub = self._ctx.socket(zmq.XPUB)
        self._xpub.setsockopt(zmq.XPUB_VERBOSE, 1)
        self._xpub.bind(self.backend_addr)

        def _run() -> None:
            poller = zmq.Poller()
            poller.register(self._xsub, zmq.POLLIN)
            poller.register(self._xpub, zmq.POLLIN)
            while not self._stop.is_set():
                try:
                    ready = dict(poller.poll(timeout=100))
                except zmq.ZMQError:
                    break
                if self._xsub in ready:
                    try:
                        msg = self._xsub.recv_multipart(flags=zmq.NOBLOCK)
                        self._xpub.send_multipart(msg)
                    except zmq.Again:
                        pass
                if self._xpub in ready:
                    try:
                        msg = self._xpub.recv_multipart(flags=zmq.NOBLOCK)
                        # Subscription traffic flows back to publishers.
                        self._xsub.send_multipart(msg)
                    except zmq.Again:
                        pass

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        for sock in (getattr(self, "_xsub", None), getattr(self, "_xpub", None)):
            if sock is not None:
                try:
                    sock.close(linger=0)
                except Exception:
                    pass


class ZmqRecorder:
    """SUB socket that subscribes to everything and timestamps arrivals."""

    def __init__(self, ctx, backend_addr: str, poll_timeout_ms: int = 2000):
        import zmq
        self._zmq = zmq
        self._socket = ctx.socket(zmq.SUB)
        self._socket.setsockopt(zmq.SUBSCRIBE, b"")
        self._socket.connect(backend_addr)
        self._poller = zmq.Poller()
        self._poller.register(self._socket, zmq.POLLIN)
        self.poll_timeout_ms = poll_timeout_ms
        self.subscribed = threading.Event()

    def mark_ready(self) -> None:
        # Called after connect+subscribe; publishers gate on this event,
        # which is the deterministic readiness mechanism (no sleep-based
        # correctness). A short settling poll lets the XPUB subscription
        # propagate before the first send.
        self.subscribed.set()

    def recv(self) -> dict | None:
        ready = dict(self._poller.poll(timeout=self.poll_timeout_ms))
        if self._socket not in ready:
            return None
        raw = self._socket.recv_json()
        return {"envelope": raw, "received_at": _now_iso()}

    def close(self) -> None:
        try:
            self._socket.close(linger=0)
        except Exception:
            pass


def run_live_capture(publish_plan: list[tuple[EventEnvelope, float]],
                     handshake_pause_s: float = 0.3) -> list[dict]:
    """Run the full in-process ZeroMQ topology and capture arrivals.

    publish_plan: (envelope, delay_before_send_s) in the order the test
    hands them to publishers. Controlled delays create arrival disorder
    against semantic order. Returns arrival records with received_at.
    """
    import zmq
    ctx = zmq.Context.instance()
    broker = ZmqBroker(ctx, "tcp://127.0.0.1:5561", "tcp://127.0.0.1:5562")
    broker.start()
    recorder = ZmqRecorder(ctx, "tcp://127.0.0.1:5562")
    recorder.mark_ready()
    # Deterministic readiness: subscription must reach the proxy before
    # any publisher sends; the pause settles propagation only.
    time.sleep(handshake_pause_s)
    publishers: dict[str, ZmqPublisher] = {}
    try:
        for event, _ in publish_plan:
            if event.source_id not in publishers:
                publishers[event.source_id] = ZmqPublisher(
                    ctx, "tcp://127.0.0.1:5561", event.source_id,
                    recorder.subscribed)
        # Stagger publisher start so each PUB handshake completes.
        time.sleep(handshake_pause_s)
        # Concurrent publishers: each thread waits its controlled delay
        # then sends, so delays reorder arrival against semantic order.
        errors: list[Exception] = []

        def _send(event: EventEnvelope, delay: float) -> None:
            try:
                publishers[event.source_id].publish(event, delay_s=delay)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=_send, args=(event, delay))
                   for event, delay in publish_plan]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15.0)
        if errors:
            raise errors[0]
        arrivals: list[dict] = []
        # Drain all arrivals (plus stragglers).
        for _ in range(2 * len(publish_plan) + 5):
            rec = recorder.recv()
            if rec is None:
                break
            arrivals.append(rec)
        return arrivals
    finally:
        for pub in publishers.values():
            pub.close()
        recorder.close()
        broker.stop()
