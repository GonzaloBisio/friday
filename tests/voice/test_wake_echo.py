"""Filtro de eco del barge-in (friday/voice/wake.py:_is_echo).

Con los parlantes de la MacBook el mic capta la voz de FRIDAY; sin este filtro
se interrumpía sola (visto en el log real del 2026-09-27).
"""

import pytest

from friday.voice.wake import _is_echo

SAID = "You're currently using six point six gigabytes, which is about fifty eight percent, sir."


@pytest.mark.parametrize("heard", [
    "currently using six point gigabytes which",   # eco limpio
    "you're currently use in six point",            # eco mal transcripto
])
def test_echo_is_ignored(heard):
    assert _is_echo(heard, SAID)


@pytest.mark.parametrize("heard", [
    "wait stop that open spotify",
    "no no tell me about the disk",
])
def test_real_interruption_passes(heard):
    assert not _is_echo(heard, SAID)


def test_empty_inputs_are_not_echo():
    assert not _is_echo("", SAID)
    assert not _is_echo("stop right there", "")


# Casos reales del log (2026-09-28): la última palabra de FRIDAY volvía como "turno".
A1 = ("It appears I cannot locate an application by that name, sir; perhaps you meant "
      "a browser tab or a specific local service?")
A2 = "It seems our services are currently unreachable, sir, or perhaps taking an extended bank holiday."


@pytest.mark.parametrize("heard,said", [("service.", A1), ("holiday.", A2)])
def test_tail_echo_is_ignored(heard, said):
    from friday.voice.wake import _is_tail_echo
    assert _is_tail_echo(heard, said)


@pytest.mark.parametrize("heard,said", [
    ("open the dashboard", A2),
    ("yes please", A1),
    ("perfect, now open spotify and play some tech house please", A1),  # largo: nunca es cola
])
def test_real_reply_is_not_tail_echo(heard, said):
    from friday.voice.wake import _is_tail_echo
    assert not _is_tail_echo(heard, said)


def test_speakable_strips_emoji_and_markdown():
    from friday.voice.wake import _speakable
    assert _speakable("✨") == ""
    assert _speakable("Done, sir! 🚀 **All** set.") == "Done, sir! All set."


# ── ¿Es para FRIDAY? (visto en el log real: respondía una charla ajena) ──────
@pytest.mark.parametrize("text,spoke,since,expected", [
    ("open the dashboard", 1.5, 3.0, True),                     # seguimiento inmediato
    ("what about the disk?", 2.0, 30.0, "fuera de la ventana de seguimiento"),
    ("friday, what about the disk?", 2.0, 30.0, True),          # la nombraste
    ("básicamente se la comenzaron la regresión el frontend", 21.9, 2.0, "muy largo sin nombrarme"),
    ("shut down", 1.0, 90.0, True),                             # comando corto: siempre
    ("stop", 0.6, 45.0, True),
])
def test_addressed_to_friday(text, spoke, since, expected):
    from friday.voice.wake import _addressed_to_friday
    assert _addressed_to_friday(text, spoke, since) == expected
