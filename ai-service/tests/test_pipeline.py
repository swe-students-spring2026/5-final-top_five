from types import SimpleNamespace
from unittest.mock import MagicMock

import pipeline
from pipeline import (
    Segment,
    Window,
    ScoredWindow,
    pack_windows,
    select_top_n,
    score_windows_mock,
)


def test_pack_windows_empty():
    assert pack_windows([]) == []


def test_pack_windows_groups_under_target():
    segs = [
        Segment(0.0, 10.0, "a"),
        Segment(10.0, 20.0, "b"),
        Segment(20.0, 28.0, "c"),
    ]
    windows = pack_windows(segs, target_sec=30.0)
    assert len(windows) == 1
    assert windows[0].start == 0.0
    assert windows[0].end == 28.0
    assert "a" in windows[0].text and "c" in windows[0].text


def test_pack_windows_splits_when_over_target():
    segs = [
        Segment(0.0, 15.0, "one"),
        Segment(15.0, 32.0, "two"),
        Segment(32.0, 50.0, "three"),
    ]
    windows = pack_windows(segs, target_sec=30.0)
    assert len(windows) >= 2
    for w in windows:
        assert w.end > w.start


def test_pack_windows_never_splits_a_segment():
    segs = [Segment(0.0, 60.0, "long single segment")]
    windows = pack_windows(segs, target_sec=30.0)
    assert len(windows) == 1
    assert windows[0].end == 60.0


def test_select_top_n_picks_highest_scores():
    w1 = Window(0, 10, "a")
    w2 = Window(20, 30, "b")
    w3 = Window(40, 50, "c")
    scored = [
        ScoredWindow(w1, 5.0),
        ScoredWindow(w2, 9.0),
        ScoredWindow(w3, 7.0),
    ]
    top = select_top_n(scored, 2)
    assert len(top) == 2
    scores = {sw.score for sw in top}
    assert scores == {9.0, 7.0}


def test_select_top_n_skips_overlapping():
    w1 = Window(0, 30, "a")
    w2 = Window(20, 50, "b")
    w3 = Window(60, 90, "c")
    scored = [
        ScoredWindow(w1, 9.0),
        ScoredWindow(w2, 8.0),
        ScoredWindow(w3, 7.0),
    ]
    top = select_top_n(scored, 2)
    assert len(top) == 2
    starts = sorted(sw.window.start for sw in top)
    assert starts == [0, 60]


def test_select_top_n_returns_empty_for_zero():
    scored = [ScoredWindow(Window(0, 10, "a"), 5.0)]
    assert select_top_n(scored, 0) == []


def test_select_top_n_results_sorted_by_start():
    w1 = Window(0, 10, "a")
    w2 = Window(20, 30, "b")
    w3 = Window(40, 50, "c")
    scored = [
        ScoredWindow(w3, 10.0),
        ScoredWindow(w1, 9.0),
        ScoredWindow(w2, 8.0),
    ]
    top = select_top_n(scored, 3)
    assert [sw.window.start for sw in top] == [0, 20, 40]


def test_transcribe_real_converts_whisper_segments(monkeypatch):
    fake_segs = [
        SimpleNamespace(start=0.0, end=5.0, text="hello"),
        SimpleNamespace(start=5.0, end=10.0, text="world"),
    ]
    fake_model = MagicMock()
    fake_model.transcribe.return_value = (iter(fake_segs), MagicMock())

    monkeypatch.setattr(pipeline, "_whisper_model", None)
    monkeypatch.setattr(pipeline, "WhisperModel", lambda *a, **k: fake_model)

    result = pipeline.transcribe_real("/path/to/video.mp4")

    assert result == [
        Segment(0.0, 5.0, "hello"),
        Segment(5.0, 10.0, "world"),
    ]
    fake_model.transcribe.assert_called_once()
    args, _kwargs = fake_model.transcribe.call_args
    assert args[0] == "/path/to/video.mp4"


def test_get_whisper_model_caches_singleton(monkeypatch):
    fake_model = MagicMock()
    factory = MagicMock(return_value=fake_model)

    monkeypatch.setattr(pipeline, "_whisper_model", None)
    monkeypatch.setattr(pipeline, "WhisperModel", factory)

    a = pipeline._get_whisper_model()
    b = pipeline._get_whisper_model()

    assert a is b is fake_model
    assert factory.call_count == 1


def test_score_windows_mock_rewards_keyword_hits():
    windows = [
        Window(0, 10, "we discuss aliens and ufos"),
        Window(10, 20, "talking about cooking recipes"),
    ]
    scored = score_windows_mock("aliens ufos government", windows)
    assert scored[0].score > scored[1].score
