"""Non-clinical mood signal for tone adaptation only."""

from __future__ import annotations

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

_analyzer: SentimentIntensityAnalyzer | None = None


def _get_analyzer() -> SentimentIntensityAnalyzer:
    global _analyzer
    if _analyzer is None:
        _analyzer = SentimentIntensityAnalyzer()
    return _analyzer


def tone_hint(text: str) -> str | None:
    """Map utterance sentiment to a private tone band for the LLM — never a diagnosis."""
    t = (text or "").strip()
    if len(t) < 3:
        return None
    scores = _get_analyzer().polarity_scores(t)
    compound = scores.get("compound", 0.0)
    if compound <= -0.35:
        return "gentle"
    if compound >= 0.45:
        return "upbeat"
    return "neutral"


def tone_hint_instruction(hint: str | None) -> str | None:
    if not hint:
        return None
    if hint == "gentle":
        return (
            "Tone hint: user seems subdued or stressed; be gentle and validating. "
            "Do not push planning or tasks unless they ask."
        )
    if hint == "upbeat":
        return "Tone hint: user seems positive; match their energy without being hyper."
    return "Tone hint: neutral; stay warm and conversational."
