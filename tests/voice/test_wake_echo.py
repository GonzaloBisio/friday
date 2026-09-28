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
