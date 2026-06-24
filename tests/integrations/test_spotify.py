"""Tests para friday.integrations.spotify — búsqueda y control de reproducción.

Todo mockeado: ni red ni token real. Se patchea `_get_access_token` para saltear
el OAuth, y `httpx.{get,put,post}` del módulo para simular la Web API.
"""

from unittest.mock import MagicMock, patch

import pytest

from friday.integrations import spotify
from friday.integrations.spotify import (
    ajustar_volumen,
    pausar_spotify,
    reproducir_spotify,
    siguiente_cancion,
)


@pytest.fixture(autouse=True)
def _clear_token_cache():
    # Evita que el access_token cacheado se filtre entre tests.
    spotify._access_cache["token"] = ""
    spotify._access_cache["expires_at"] = 0.0
    yield


def _resp(status=200, json_data=None):
    m = MagicMock()
    m.status_code = status
    m.json.return_value = json_data or {}
    m.text = ""
    return m


def _search(tipo, uri, name):
    return _resp(json_data={f"{tipo}s": {"items": [{"uri": uri, "name": name}]}})


def _devices(active=True):
    return _resp(json_data={"devices": [{"id": "dev1", "is_active": active}]})


class TestReproducir:
    def test_plays_playlist_on_active_device(self):
        with patch.object(spotify, "_get_access_token", return_value="tok"), \
             patch.object(spotify.httpx, "get",
                          side_effect=[_search("playlist", "spotify:playlist:1", "Tech House"),
                                       _devices()]), \
             patch.object(spotify.httpx, "put", return_value=_resp(204)) as put:
            result = reproducir_spotify("Tech House")
        assert result == "Reproduciendo playlist 'Tech House' en Spotify."
        # Playlist → context_uri (no uris).
        assert put.call_args.kwargs["json"] == {"context_uri": "spotify:playlist:1"}
        assert put.call_args.kwargs["params"] == {"device_id": "dev1"}

    def test_track_uses_uris_not_context(self):
        with patch.object(spotify, "_get_access_token", return_value="tok"), \
             patch.object(spotify.httpx, "get",
                          side_effect=[_search("track", "spotify:track:9", "Song"),
                                       _devices()]), \
             patch.object(spotify.httpx, "put", return_value=_resp(204)) as put:
            result = reproducir_spotify("Song", tipo="track")
        assert "Reproduciendo track 'Song'" in result
        assert put.call_args.kwargs["json"] == {"uris": ["spotify:track:9"]}

    def test_no_active_device_is_honest(self):
        with patch.object(spotify, "_get_access_token", return_value="tok"), \
             patch.object(spotify.httpx, "get",
                          side_effect=[_search("playlist", "spotify:playlist:1", "X"),
                                       _resp(json_data={"devices": []})]), \
             patch.object(spotify.httpx, "put") as put:
            result = reproducir_spotify("X")
        assert "no hay ningún dispositivo" in result.lower()
        assert "abrí la app de spotify" in result.lower()
        put.assert_not_called()

    def test_not_found(self):
        with patch.object(spotify, "_get_access_token", return_value="tok"), \
             patch.object(spotify.httpx, "get",
                          return_value=_resp(json_data={"playlists": {"items": []}})):
            result = reproducir_spotify("no existe esto")
        assert "no encontré" in result.lower()

    def test_premium_required(self):
        with patch.object(spotify, "_get_access_token", return_value="tok"), \
             patch.object(spotify.httpx, "get",
                          side_effect=[_search("playlist", "spotify:playlist:1", "X"),
                                       _devices()]), \
             patch.object(spotify.httpx, "put", return_value=_resp(403)):
            result = reproducir_spotify("X")
        assert "premium" in result.lower()

    def test_unknown_type_falls_back_to_playlist(self):
        with patch.object(spotify, "_get_access_token", return_value="tok"), \
             patch.object(spotify.httpx, "get",
                          side_effect=[_search("playlist", "spotify:playlist:1", "X"),
                                       _devices()]) as get, \
             patch.object(spotify.httpx, "put", return_value=_resp(204)):
            reproducir_spotify("X", tipo="banana")
        # La búsqueda se hizo con type=playlist (fallback), no "banana".
        assert get.call_args_list[0].kwargs["params"]["type"] == "playlist"

    def test_falls_back_to_track_when_type_empty(self):
        # Pide playlist (default) pero solo existe como track → debe matchear
        # track y confirmarlo honestamente (no decir "playlist").
        empty_playlist = _resp(json_data={"playlists": {"items": []}})
        track_hit = _search("track", "spotify:track:9", "Rock n Roll Train")
        with patch.object(spotify, "_get_access_token", return_value="tok"), \
             patch.object(spotify.httpx, "get",
                          side_effect=[empty_playlist, track_hit, _devices()]), \
             patch.object(spotify.httpx, "put", return_value=_resp(204)) as put:
            result = reproducir_spotify("Rock n Roll Train")
        assert "track 'Rock n Roll Train'" in result
        assert put.call_args.kwargs["json"] == {"uris": ["spotify:track:9"]}

    def test_empty_query(self):
        result = reproducir_spotify("   ")
        assert "qué reproducir" in result.lower()

    def test_not_authorized_surfaces_clean_message(self, tmp_path):
        # Sin token guardado → mensaje claro de "corré friday-spotify-auth".
        missing = tmp_path / "nope.json"
        with patch.object(spotify.settings, "spotify_token_path", str(missing)):
            result = reproducir_spotify("X")
        assert "no pude reproducir" in result.lower()
        assert "autorizado" in result.lower()


class TestPausar:
    def test_pauses(self):
        with patch.object(spotify, "_get_access_token", return_value="tok"), \
             patch.object(spotify.httpx, "put", return_value=_resp(204)):
            assert pausar_spotify() == "Pausado."

    def test_nothing_playing(self):
        with patch.object(spotify, "_get_access_token", return_value="tok"), \
             patch.object(spotify.httpx, "put", return_value=_resp(404)):
            assert "no hay reproducción" in pausar_spotify().lower()


class TestSiguiente:
    def test_skips(self):
        with patch.object(spotify, "_get_access_token", return_value="tok"), \
             patch.object(spotify.httpx, "post", return_value=_resp(204)):
            assert siguiente_cancion() == "Siguiente."


class TestVolumen:
    def test_sets_volume(self):
        with patch.object(spotify, "_get_access_token", return_value="tok"), \
             patch.object(spotify.httpx, "put", return_value=_resp(204)) as put:
            assert ajustar_volumen(70) == "Volumen al 70%."
        assert put.call_args.kwargs["params"] == {"volume_percent": 70}

    def test_clamps_above_100(self):
        with patch.object(spotify, "_get_access_token", return_value="tok"), \
             patch.object(spotify.httpx, "put", return_value=_resp(204)) as put:
            assert ajustar_volumen(150) == "Volumen al 100%."
        assert put.call_args.kwargs["params"] == {"volume_percent": 100}

    def test_invalid_value(self):
        result = ajustar_volumen("fuerte")  # type: ignore[arg-type]
        assert "entre 0 y 100" in result

    def test_no_device(self):
        with patch.object(spotify, "_get_access_token", return_value="tok"), \
             patch.object(spotify.httpx, "put", return_value=_resp(404)):
            assert "no hay dispositivo" in ajustar_volumen(50).lower()
