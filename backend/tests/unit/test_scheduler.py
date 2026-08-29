"""Inner loop: the automatic-ingestion poller (plan.md Phase 8).

`poll_forever` is exercised with a fake `wait` that returns instantly, so these tests
never really sleep. `IngestionScheduler`'s start/stop lifecycle is exercised on a real
background thread, synchronised with a `threading.Event` rather than a fixed sleep.
"""

import threading

import pytest

from app.ingestion.scheduler import IngestionScheduler, poll_forever


class TestPollForever:
    def test_calls_sync_fn_once_before_the_first_wait(self) -> None:
        calls = []

        poll_forever(
            sync_fn=lambda: calls.append(1), wait=lambda seconds: True, interval_seconds=0.001
        )

        assert calls == [1]

    def test_keeps_calling_sync_fn_until_wait_signals_stop(self) -> None:
        calls = []
        stop_after = iter([False, False, True])

        poll_forever(
            sync_fn=lambda: calls.append(1),
            wait=lambda seconds: next(stop_after),
            interval_seconds=0.001,
        )

        assert len(calls) == 3

    def test_passes_interval_seconds_through_to_wait(self) -> None:
        received = []

        def wait(seconds):
            received.append(seconds)
            return True

        poll_forever(sync_fn=lambda: None, wait=wait, interval_seconds=42)

        assert received == [42]

    def test_a_failing_tick_does_not_stop_the_next_one(self) -> None:
        calls = []
        stop_after = iter([False, True])

        def sync_fn():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("boom")

        poll_forever(sync_fn=sync_fn, wait=lambda seconds: next(stop_after), interval_seconds=0.001)

        assert len(calls) == 2


class TestIngestionScheduler:
    def test_start_calls_sync_fn_on_a_background_thread(self) -> None:
        called = threading.Event()
        scheduler = IngestionScheduler(sync_fn=called.set, interval_seconds=10)

        scheduler.start()
        try:
            assert called.wait(timeout=1), "sync_fn was never called"
        finally:
            scheduler.stop()

    def test_start_is_idempotent(self) -> None:
        calls = threading.Event()
        scheduler = IngestionScheduler(sync_fn=calls.set, interval_seconds=10)

        scheduler.start()
        assert calls.wait(timeout=1)
        first_thread = scheduler._thread
        scheduler.start()

        assert scheduler._thread is first_thread
        scheduler.stop()

    def test_stop_before_start_does_not_raise(self) -> None:
        scheduler = IngestionScheduler(sync_fn=lambda: None, interval_seconds=10)

        scheduler.stop()

    def test_stop_joins_the_thread(self) -> None:
        called = threading.Event()
        scheduler = IngestionScheduler(sync_fn=called.set, interval_seconds=10)
        scheduler.start()
        assert called.wait(timeout=1)

        scheduler.stop()

        assert scheduler._thread is None

    @pytest.mark.integration
    def test_a_second_tick_runs_after_the_interval_elapses(self) -> None:
        """The one genuinely timing-dependent behaviour — marked integration, excluded by
        default, so the fast suite never depends on real wall-clock timing."""
        tick_count = threading.Event()
        calls = []

        def sync_fn():
            calls.append(1)
            if len(calls) == 2:
                tick_count.set()

        scheduler = IngestionScheduler(sync_fn=sync_fn, interval_seconds=0.05)
        scheduler.start()
        try:
            assert tick_count.wait(timeout=2), "expected a second tick after the interval"
        finally:
            scheduler.stop()
