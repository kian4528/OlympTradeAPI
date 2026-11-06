import csv

import pytest

from olymptrade_ws.strategy.tick_recorder import TickRecorder


def test_tick_recorder_batches_disk_flushes_and_flushes_signals_immediately(tmp_path):
    recorder = TickRecorder(tmp_path, flush_every=2)
    try:
        recorder.record_tick("EURUSD", 1, 1.1)
        assert len(recorder.file_path.read_text(encoding="utf-8").splitlines()) == 1

        recorder.record_tick("EURUSD", 2, 1.2)
        rows = list(csv.DictReader(recorder.file_path.open(encoding="utf-8")))
        assert len(rows) == 2

        recorder.record_tick("EURUSD", 3, 1.3)
        recorder.record_signal("EURUSD", 4, 1.4, "test", "up", "signal")
        rows = list(csv.DictReader(recorder.file_path.open(encoding="utf-8")))
        assert len(rows) == 4
    finally:
        recorder.close()


def test_tick_recorder_rejects_invalid_flush_interval(tmp_path):
    for value in (0, -1, True, 1.5):
        with pytest.raises(ValueError):
            TickRecorder(tmp_path, flush_every=value)
