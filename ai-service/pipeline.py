from dataclasses import dataclass


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class Window:
    start: float
    end: float
    text: str


@dataclass
class ScoredWindow:
    window: Window
    score: float
    reason: str = ""


def pack_windows(segments: list[Segment], target_sec: float = 30.0) -> list[Window]:
    if not segments:
        return []

    windows: list[Window] = []
    buf: list[Segment] = []
    buf_start = segments[0].start

    for seg in segments:
        if buf and (seg.end - buf_start) > target_sec:
            windows.append(
                Window(
                    start=buf_start,
                    end=buf[-1].end,
                    text=" ".join(s.text.strip() for s in buf).strip(),
                )
            )
            buf = []
            buf_start = seg.start
        buf.append(seg)

    if buf:
        windows.append(
            Window(
                start=buf_start,
                end=buf[-1].end,
                text=" ".join(s.text.strip() for s in buf).strip(),
            )
        )

    return windows


def select_top_n(scored: list[ScoredWindow], n: int) -> list[ScoredWindow]:
    if n <= 0 or not scored:
        return []

    ordered = sorted(scored, key=lambda s: s.score, reverse=True)
    chosen: list[ScoredWindow] = []

    for cand in ordered:
        if len(chosen) >= n:
            break
        if any(_overlaps(cand.window, c.window) for c in chosen):
            continue
        chosen.append(cand)

    chosen.sort(key=lambda s: s.window.start)
    return chosen


def _overlaps(a: Window, b: Window) -> bool:
    return a.start < b.end and b.start < a.end


def transcribe_mock(video_path: str) -> list[Segment]:
    return [
        Segment(start=0.0, end=8.0, text="Welcome to the show."),
        Segment(start=8.0, end=20.0, text="Today we are talking about aliens and UFOs."),
        Segment(start=20.0, end=35.0, text="My guest claims he saw a craft over Nevada last summer."),
        Segment(start=35.0, end=55.0, text="Then we shifted to economics and inflation policy."),
        Segment(start=55.0, end=80.0, text="The guest returned to alien lore and government cover-ups."),
        Segment(start=80.0, end=110.0, text="We closed with listener questions about cooking."),
    ]


def score_windows_mock(prompt: str, windows: list[Window]) -> list[ScoredWindow]:
    keywords = [w.lower() for w in prompt.split() if len(w) > 3]
    scored = []
    for win in windows:
        text = win.text.lower()
        hits = sum(1 for k in keywords if k in text)
        score = min(10.0, 2.0 + 2.5 * hits)
        scored.append(ScoredWindow(window=win, score=score, reason=f"{hits} keyword hits"))
    return scored


def cut_clip_mock(video_path: str, start: float, end: float, out_path: str) -> str:
    return out_path
