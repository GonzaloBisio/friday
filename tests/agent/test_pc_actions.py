"""Tests para friday.agent.actions.pc_actions — acciones concretas de PC."""

from unittest.mock import MagicMock, patch

import pytest

from friday import platform_info
from friday.agent.actions.pc_actions import (
    abrir_app,
    abrir_url,
    buscar_en_google,
    cerrar_app,
    info_sistema,
    leer_archivo,
    listar_directorio,
    listar_procesos,
)

RUN = "friday.agent.actions.pc_actions.subprocess.run"


@pytest.fixture(autouse=True)
def _pin_macos(monkeypatch):
    monkeypatch.setattr(platform_info, "PLATFORM", platform_info.MACOS)


def _run_ok(stdout="", stderr=""):
    m = MagicMock()
    m.returncode = 0
    m.stdout, m.stderr = stdout, stderr
    return m


def _run_fail(stderr="cannot find"):
    m = MagicMock()
    m.returncode = 1
    m.stdout, m.stderr = "", stderr
    return m


class TestAbrirApp:
    @patch(RUN)
    def test_resolves_alias_with_open_a(self, mock_run):
        mock_run.return_value = _run_ok()
        result = abrir_app("chrome")
        assert "abrí" in result.lower()
        assert mock_run.call_args[0][0] == ["open", "-a", "Google Chrome"]

    @patch(RUN)
    def test_unknown_name_passes_as_single_arg_without_shell(self, mock_run):
        mock_run.return_value = _run_ok()
        abrir_app("Figma; rm -rf ~")
        assert mock_run.call_args[0][0] == ["open", "-a", "Figma; rm -rf ~"]
        assert mock_run.call_args.kwargs.get("shell") in (None, False)

    @patch(RUN)
    def test_reports_failure_honestly(self, mock_run):
        mock_run.return_value = _run_fail("Unable to find application named 'Nope'")
        result = abrir_app("Nope")
        assert "no pude" in result.lower() and "unable to find" in result.lower()

    @patch(RUN, side_effect=FileNotFoundError)
    def test_missing_binary(self, mock_run):
        assert "no encuentro" in abrir_app("notepad").lower()

    def test_empty_name(self):
        assert "qué app" in abrir_app("   ").lower()

    @patch(RUN)
    def test_unsupported_platform(self, mock_run, monkeypatch):
        monkeypatch.setattr(platform_info, "PLATFORM", platform_info.LINUX)
        assert "todavía no sé" in abrir_app("chrome").lower()
        mock_run.assert_not_called()


class TestCerrarApp:
    @patch(RUN)
    def test_quits_via_osascript_with_argv(self, mock_run):
        mock_run.return_value = _run_ok(stdout="ok\n")
        result = cerrar_app("spotify")
        assert "cerré" in result.lower()
        args = mock_run.call_args[0][0]
        assert args[0] == "osascript" and args[-1] == "Spotify"

    @patch(RUN)
    def test_not_running_is_honest(self, mock_run):
        mock_run.return_value = _run_ok(stdout="not_running\n")
        assert "no estaba abierta" in cerrar_app("spotify").lower()

    @patch(RUN)
    def test_failure_honest(self, mock_run):
        mock_run.return_value = _run_fail("execution error: not allowed")
        result = cerrar_app("spotify")
        assert "no pude" in result.lower() and "not allowed" in result.lower()

    def test_empty_name(self):
        assert "qué app" in cerrar_app("   ").lower()


class TestAbrirUrl:
    @patch(RUN)
    def test_opens_with_open(self, mock_run):
        mock_run.return_value = _run_ok()
        assert "abrí" in abrir_url("https://github.com").lower()
        assert mock_run.call_args[0][0] == ["open", "https://github.com"]

    @patch(RUN)
    def test_preserves_ampersand_in_query(self, mock_run):
        mock_run.return_value = _run_ok()
        abrir_url("https://www.youtube.com/watch?v=abc&list=xyz")
        assert mock_run.call_args[0][0][-1] == "https://www.youtube.com/watch?v=abc&list=xyz"

    @patch(RUN)
    def test_accepts_spotify_scheme(self, mock_run):
        mock_run.return_value = _run_ok()
        assert "abrí" in abrir_url("spotify:search:tech house").lower()

    @patch(RUN)
    def test_linux_uses_xdg_open(self, mock_run, monkeypatch):
        monkeypatch.setattr(platform_info, "PLATFORM", platform_info.LINUX)
        mock_run.return_value = _run_ok()
        abrir_url("https://x.com")
        assert mock_run.call_args[0][0][0] == "xdg-open"

    @pytest.mark.parametrize("bad", ["file:///etc/passwd", "javascript:alert(1)",
                                     "https://x.com\nrm -rf ~"])
    @patch(RUN)
    def test_rejects_unsafe(self, mock_run, bad):
        assert "no válida" in abrir_url(bad).lower()
        mock_run.assert_not_called()

    def test_empty_url(self):
        assert "qué url" in abrir_url("   ").lower()

    @patch(RUN)
    def test_reports_failure_honestly(self, mock_run):
        mock_run.return_value = _run_fail("LSOpenURLsWithRole() failed")
        assert "no pude" in abrir_url("https://x.com").lower()


class TestBuscarEnGoogle:
    @patch(RUN)
    def test_builds_encoded_search_url(self, mock_run):
        mock_run.return_value = _run_ok()
        result = buscar_en_google("clima Córdoba")
        assert "buscando" in result.lower()
        url = mock_run.call_args[0][0][-1]
        assert "google.com/search?q=" in url
        assert "clima+C" in url  # espacio → '+', acento percent-encoded

    @patch(RUN)
    def test_propagates_error(self, mock_run):
        mock_run.return_value = _run_fail("falló")
        assert "no pude" in buscar_en_google("algo").lower()

    def test_empty_query(self):
        assert "qué buscar" in buscar_en_google("  ").lower()


class TestListarProcesos:
    @patch("friday.agent.actions.pc_actions.psutil.process_iter")
    def test_returns_process_list(self, mock_iter):
        mem = MagicMock()
        mem.rss = 500 * 1024 * 1024  # 500 MB

        proc = MagicMock()
        proc.info = {"pid": 1234, "name": "python.exe", "cpu_percent": 5.0, "memory_info": mem}

        mock_iter.return_value = [proc]
        result = listar_procesos(top=5)
        assert "python.exe" in result
        assert "1234" in result

    @patch("friday.agent.actions.pc_actions.psutil.process_iter", return_value=[])
    def test_handles_empty(self, mock_iter):
        result = listar_procesos()
        assert "no se encontraron" in result.lower()


class TestLeerArchivo:
    def test_reads_existing_file(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("linea1\nlinea2\nlinea3", encoding="utf-8")
        result = leer_archivo(str(f))
        assert "linea1" in result
        assert "linea3" in result

    def test_truncates_long_file(self, tmp_path):
        f = tmp_path / "long.txt"
        f.write_text("\n".join(f"linea {i}" for i in range(200)), encoding="utf-8")
        result = leer_archivo(str(f), max_lineas=10)
        assert "190 líneas más" in result

    def test_file_not_found(self):
        result = leer_archivo("/ruta/que/no/existe.txt")
        assert "no encontrado" in result.lower()

    def test_not_a_file(self, tmp_path):
        result = leer_archivo(str(tmp_path))
        assert "no es un archivo" in result.lower()


class TestInfoSistema:
    @patch("friday.agent.actions.pc_actions.psutil.cpu_percent", return_value=25.0)
    @patch("friday.agent.actions.pc_actions.psutil.cpu_count", side_effect=[4, 8])
    @patch("friday.agent.actions.pc_actions.psutil.boot_time", return_value=1718000000.0)
    def test_returns_system_info(self, mock_boot, mock_count, mock_cpu):
        mem = MagicMock()
        mem.used = 8 * 1024**3
        mem.total = 16 * 1024**3
        mem.percent = 50.0

        disk = MagicMock()
        disk.used = 200 * 1024**3
        disk.total = 500 * 1024**3
        disk.percent = 40.0

        net = MagicMock()
        net.bytes_sent = 1024**3
        net.bytes_recv = 5 * 1024**3

        with patch("friday.agent.actions.pc_actions.psutil.virtual_memory", return_value=mem), \
             patch("friday.agent.actions.pc_actions.psutil.disk_usage", return_value=disk), \
             patch("friday.agent.actions.pc_actions.psutil.net_io_counters", return_value=net), \
             patch("friday.agent.actions.pc_actions.psutil.time") as mock_time:
            mock_time.time.return_value = 1718100000.0
            result = info_sistema()

        assert "CPU" in result
        assert "RAM" in result
        assert "Disco" in result


class TestListarDirectorio:
    def test_lists_directory(self, tmp_path):
        (tmp_path / "archivo.txt").write_text("hola")
        (tmp_path / "subdir").mkdir()
        result = listar_directorio(str(tmp_path))
        assert "archivo.txt" in result
        assert "subdir" in result
        assert "FILE" in result
        assert "DIR" in result

    def test_dir_not_found(self):
        result = listar_directorio("/no/existe")
        assert "no encontrado" in result.lower()

    def test_not_a_directory(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_text("x")
        result = listar_directorio(str(f))
        assert "no es un directorio" in result.lower()



class TestAbrirDashboard:
    @patch(RUN)
    def test_opens_local_hud(self, mock_run):
        mock_run.return_value = _run_ok()
        from friday.agent.actions.pc_actions import abrir_dashboard
        from friday.config import settings
        assert "command center" in abrir_dashboard().lower()
        assert mock_run.call_args[0][0] == ["open", f"http://127.0.0.1:{settings.api_port}/"]
