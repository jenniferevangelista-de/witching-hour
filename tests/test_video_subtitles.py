"""Subtitle and narration-contract checks without loading the render stack."""
import ast
import json
import re
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "video" / "make_videos.py"
TREE = ast.parse(SCRIPT.read_text(encoding="utf-8"), filename=str(SCRIPT))
SELECTED = {"split_cue", "warning_case", "recorded_guardian"}
NAMESPACE = {
    "re": re, "textwrap": textwrap, "json": json, "Path": Path, "ROOT": ROOT,
}
# Only these pure/text/fixture helpers are compiled; render imports and entry
# points are never imported or executed by these tests.
HELPERS = ast.Module(
    body=[
        node for node in TREE.body
        if isinstance(node, ast.FunctionDef) and node.name in SELECTED
    ],
    type_ignores=[],
)
exec(compile(HELPERS, str(SCRIPT), "exec"), NAMESPACE)
split_cue = NAMESPACE["split_cue"]


def literal(name):
    for node in TREE.body:
        if (
            isinstance(node, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == name for t in node.targets)
        ):
            return ast.literal_eval(node.value)
    raise AssertionError(f"Missing literal: {name}")


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        (
            "This is the live demo of Witching Hour. I'm Luna, and I'll show you around.",
            5.184,
        ),
        (
            "Every strange night becomes a case file. I tell the story, "
            "Doctor Bigotes explains it, and Xochi writes the note. "
            "Every sentence must cite its evidence, and every number must match. "
            "Otherwise, it vanishes.",
            14.184,
        ),
        (
            "A flicker; an ordinary explanation. The measurements are real, "
            "but the spirit is fictional. Keep both ideas together.",
            8.0,
        ),
    ],
)
def test_cues_preserve_text_and_avoid_subsecond_orphan_fragments(text, seconds):
    cues = split_cue(text, seconds)
    assert " ".join(c[2] for c in cues) == " ".join(text.split())
    assert cues[0][0] == 0
    assert cues[-1][1] == pytest.approx(seconds)
    assert all(end - start >= 1.0 for start, end, _ in cues)
    assert all(len(c[2].split()) > 1 for c in cues)
    for previous, following in zip(cues, cues[1:]):
        assert previous[1] == pytest.approx(following[0])


def test_empty_and_unusable_durations_have_no_cues():
    assert split_cue("   ", 4) == []
    assert split_cue("A sentence.", 0) == []
    assert split_cue("A sentence.", -1) == []


def test_short_whole_utterance_keeps_its_actual_duration():
    assert split_cue("Yes.", .3) == [(0.0, .3, "Yes.")]


def test_unicode_and_whitespace_are_preserved_semantically():
    text = "  Día de los Muertos.\n\t“Measured events; fictional spirits.”  "
    cues = split_cue(text, 6.0)
    assert " ".join(c[2] for c in cues) == " ".join(text.split())


def test_scripts_disclose_fiction_privacy_and_both_voice_sources():
    film = literal("FILM")
    tour = literal("TOUR")
    film_words = " ".join(line for scene in film for _, line in scene[2])
    tour_words = " ".join(line for _, line in tour)
    assert "spirits are fiction" in film[0][2][0][1].lower()
    assert "spirits are fictional" in tour[0][1].lower()
    assert "Nothing is uploaded" not in film_words + tour_words
    assert "every minute" not in film_words + tour_words
    assert "ten-minute slot" in film_words
    assert "Measured events and your questions go to" in film_words
    for words in (film_words, tour_words):
        assert "Microsoft Edge TTS" in words
        assert "ElevenLabs" in words
    assert [scene[3] for scene in film if len(scene) > 3] == [0]


def test_guardian_excerpt_matches_the_first_real_recorded_reply():
    case = NAMESPACE["warning_case"]()
    path, spoken = NAMESPACE["recorded_guardian"](case, 0)
    assert path == ROOT / "demo_data" / "media" / "the_warning" / "turn-1.mp3"
    assert path.is_file()
    assert spoken == case["seance"]["turns"][0]["response"]["spoken"]
    assert case["seance"]["turns"][0]["response"]["fictional"] is True


def test_existing_character_voice_choices_are_preserved():
    assert literal("VOICE") == {
        "luna": "en-US-AvaMultilingualNeural",
        "bigotes": "en-GB-RyanNeural",
        "xochi": "en-US-EmmaMultilingualNeural",
    }
