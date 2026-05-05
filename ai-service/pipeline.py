import json
import os
import re
import subprocess

from dataclasses import dataclass

import requests
from faster_whisper import WhisperModel


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


_whisper_model: WhisperModel | None = None


def _get_whisper_model() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        name = os.getenv("WHISPER_MODEL", "base.en")
        _whisper_model = WhisperModel(name, device="cpu", compute_type="int8")
    return _whisper_model


def transcribe_real(video_path: str) -> list[Segment]:
    model = _get_whisper_model()
    segs, _info = model.transcribe(
        video_path,
        beam_size=1,
        vad_filter=True,
    )
    return [Segment(start=float(s.start), end=float(s.end), text=s.text) for s in segs]


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


_SCORING_SYSTEM_PROMPT = (
    "You score video transcript windows against a user query. "
    "For each window, return a score from 0 to 10 indicating how well the window matches the query. "
    "10 means the window directly and richly addresses the query. "
    "0 means the window is unrelated. "
    "Return strict JSON only, no markdown, no commentary. "
    'Format: {"scores": [{"idx": 0, "score": 8.5, "reason": "short explanation"}, ...]}'
)


def score_windows_real(prompt: str, windows: list[Window]) -> list[ScoredWindow]:
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key or not windows:
        return score_windows_mock(prompt, windows)

    model = os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
    user_msg_lines = [f"Query: {prompt}", "", "Windows:"]
    for i, w in enumerate(windows):
        user_msg_lines.append(f"[{i}] ({w.start:.1f}s-{w.end:.1f}s): {w.text}")
    user_msg = "\n".join(user_msg_lines)

    try:
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [
                    {"role": "user", "content": f"{_SCORING_SYSTEM_PROMPT}\n\n{user_msg}"},
                ],
            },
            timeout=60,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"].strip()
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
        data = json.loads(content)
        by_idx = {int(s["idx"]): s for s in data.get("scores", [])}
    except Exception as exc:
        print(f"[score_windows_real] OpenRouter call failed ({exc}); falling back to mock")
        return score_windows_mock(prompt, windows)

    scored: list[ScoredWindow] = []
    for i, win in enumerate(windows):
        entry = by_idx.get(i, {})
        try:
            raw_score = float(entry.get("score", 0.0))
        except (TypeError, ValueError):
            raw_score = 0.0
        scored.append(
            ScoredWindow(
                window=win,
                score=max(0.0, min(10.0, raw_score)),
                reason=str(entry.get("reason", "")),
            )
        )
    return scored


def cut_clip_real(video_path: str, start: float, end: float, out_path: str) -> str:
    duration = end - start

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-ss", str(start),
            "-t", str(duration),
            "-c:v", "libx264",
            "-c:a", "aac",
            out_path,
        ],
        check=True,
    )

    return out_path
