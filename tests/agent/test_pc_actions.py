"""Tests para friday.agent.actions.pc_actions — acciones concretas de PC."""

from unittest.mock import MagicMock, patch

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
    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_opens_app(self, mock_run):
        mock_run.return_value = _run_ok()
        result = abrir_app("notepad")
        assert "notepad" in result
        assert "abrí" in result.lower()
        # Cruza por cmd.exe con argv como lista (sin shell=True)
        args = mock_run.call_args[0][0]
        assert args[0] == "cmd.exe"
        assert "notepad" in args

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_spotify_alias_resolves_to_uri(self, mock_run):
        mock_run.return_value = _run_ok()
        abrir_app("Spotify")
        args = mock_run.call_args[0][0]
        assert "spotify:" in args  # alias → URI

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_reports_failure_honestly(self, mock_run):
        mock_run.return_value = _run_fail("Windows cannot find 'inexistente'")
        result = abrir_app("inexistente")
        assert "no pude" in result.lower()
        assert "cannot find" in result.lower()

    @patch("friday.agent.actions.pc_actions.subprocess.run", side_effect=FileNotFoundError)
    def test_interop_missing(self, mock_run):
        result = abrir_app("notepad")
        assert "interop" in result.lower()

    def test_empty_name(self):
        assert "qué app" in abrir_app("   ").lower()

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_rejects_injection(self, mock_run):
        result = abrir_app("foo & calc")
        assert "no válido" in result.lower()
        mock_run.assert_not_called()

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_decodes_oem_codepage_tolerantly(self, mock_run):
        # cmd.exe escribe en codepage OEM, no UTF-8 → debe decodificar tolerante.
        mock_run.return_value = _run_ok()
        abrir_app("notepad")
        assert mock_run.call_args.kwargs.get("errors") == "replace"


class TestCerrarApp:
    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_closes_app(self, mock_run):
        mock_run.return_value = _run_ok("SUCCESS: ...")
        result = cerrar_app("spotify")
        assert "cerré" in result.lower()
        # Cruza por cmd.exe con taskkill /IM Spotify.exe /F
        args = mock_run.call_args[0][0]
        assert args[0] == "cmd.exe"
        assert "taskkill" in args
        assert "Spotify.exe" in args
        assert "/F" in args

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_spotify_alias_to_process_name(self, mock_run):
        mock_run.return_value = _run_ok()
        cerrar_app("Spotify")
        args = mock_run.call_args[0][0]
        assert "Spotify.exe" in args

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_not_running_is_honest(self, mock_run):
        # taskkill devuelve 128 cuando no encuentra el proceso.
        m = MagicMock()
        m.returncode = 128
        m.stdout = "ERROR: no running task found with name 'Spotify.exe'"
        m.stderr = ""
        mock_run.return_value = m
        result = cerrar_app("spotify")
        assert "no estaba abierta" in result.lower()

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_failure_honest(self, mock_run):
        # returncode != 0 y no es "not found" → error real (access denied, etc.)
        mock_run.return_value = _run_fail("access denied")
        result = cerrar_app("spotify")
        assert "no pude" in result.lower()
        assert "access denied" in result.lower()

    @patch("friday.agent.actions.pc_actions.subprocess.run", side_effect=FileNotFoundError)
    def test_interop_missing(self, mock_run):
        result = cerrar_app("notepad")
        assert "interop" in result.lower()

    def test_empty_name(self):
        assert "qué app" in cerrar_app("   ").lower()

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_rejects_injection(self, mock_run):
        result = cerrar_app("foo & calc")
        assert "no válido" in result.lower()
        mock_run.assert_not_called()

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_unknown_app_appends_exe(self, mock_run):
        # App no mapeada → asume .exe y sanitiza.
        mock_run.return_value = _run_ok()
        cerrar_app("discord")
        args = mock_run.call_args[0][0]
        assert "discord.exe" in args

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_calculator_uwp_tries_app_first(self, mock_run):
        """Calculator es UWP: prueba CalculatorApp.exe primero (el proceso
        real), no calc.exe (el launcher que ya se autocierró)."""
        mock_run.return_value = _run_ok("SUCCESS")
        cerrar_app("calculator")
        # Primera call debe ser CalculatorApp.exe, no calc.exe
        first_call_args = mock_run.call_args_list[0][0][0]
        assert "CalculatorApp.exe" in first_call_args

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_calculator_falls_back_to_launcher(self, mock_run):
        """Si CalculatorApp.exe no está, prueba calc.exe como fallback."""
        not_found = MagicMock()
        not_found.returncode = 128
        not_found.stdout = "ERROR: no running task 'CalculatorApp.exe'"
        not_found.stderr = ""
        ok = _run_ok("SUCCESS")
        mock_run.side_effect = [not_found, ok]
        result = cerrar_app("calculator")
        assert "cerré" in result.lower()
        # Dos calls: CalculatorApp.exe (no encontró) → calc.exe (éxito)
        assert mock_run.call_count == 2

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_calculator_neither_running(self, mock_run):
        """Si ni CalculatorApp.exe ni calc.exe están corriendo → 'no estaba
        abierta'."""
        not_found = MagicMock()
        not_found.returncode = 128
        not_found.stdout = "ERROR: no running task"
        not_found.stderr = ""
        mock_run.side_effect = [not_found, not_found]
        result = cerrar_app("calculator")
        assert "no estaba abierta" in result.lower()
        assert mock_run.call_count == 2


class TestAbrirUrl:
    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_opens_url_via_powershell_start_process(self, mock_run):
        mock_run.return_value = _run_ok()
        result = abrir_url("https://github.com")
        assert "abrí" in result.lower()
        args = mock_run.call_args[0][0]
        assert args[0] == "powershell.exe"
        # La URL viaja dentro del -Command como Start-Process '...'
        cmd = args[-1]
        assert "Start-Process" in cmd
        assert "https://github.com" in cmd

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_preserves_ampersand_in_query(self, mock_run):
        # El motivo de existir de esta función: el & no debe partirse.
        mock_run.return_value = _run_ok()
        abrir_url("https://www.youtube.com/watch?v=abc&list=xyz")
        cmd = mock_run.call_args[0][0][-1]
        assert "v=abc&list=xyz" in cmd

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_accepts_spotify_scheme(self, mock_run):
        mock_run.return_value = _run_ok()
        result = abrir_url("spotify:search:tech house")
        assert "abrí" in result.lower()
        assert args_ok(mock_run, "spotify:search")

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_rejects_non_web_scheme(self, mock_run):
        result = abrir_url("file:///etc/passwd")
        assert "no válida" in result.lower()
        mock_run.assert_not_called()

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_rejects_javascript_scheme(self, mock_run):
        result = abrir_url("javascript:alert(1)")
        assert "no válida" in result.lower()
        mock_run.assert_not_called()

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_escapes_single_quote(self, mock_run):
        # Comilla simple → duplicada, para no romper el string de PowerShell.
        mock_run.return_value = _run_ok()
        abrir_url("https://x.com/a'b")
        cmd = mock_run.call_args[0][0][-1]
        assert "a''b" in cmd

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_rejects_newline(self, mock_run):
        result = abrir_url("https://x.com\nStart-Process calc")
        assert "no válida" in result.lower()
        mock_run.assert_not_called()

    def test_empty_url(self):
        assert "qué url" in abrir_url("   ").lower()

    @patch("friday.agent.actions.pc_actions.subprocess.run", side_effect=FileNotFoundError)
    def test_interop_missing(self, mock_run):
        result = abrir_url("https://x.com")
        assert "interop" in result.lower()

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_reports_failure_honestly(self, mock_run):
        mock_run.return_value = _run_fail("Start-Process : algo falló")
        result = abrir_url("https://x.com")
        assert "no pude" in result.lower()


class TestBuscarEnGoogle:
    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_builds_encoded_search_url(self, mock_run):
        mock_run.return_value = _run_ok()
        result = buscar_en_google("clima Córdoba")
        assert "buscando" in result.lower()
        cmd = mock_run.call_args[0][0][-1]
        assert "google.com/search?q=" in cmd
        # Espacio → '+', acento → percent-encoded (quote_plus).
        assert "clima+C" in cmd

    @patch("friday.agent.actions.pc_actions.subprocess.run")
    def test_propagates_error(self, mock_run):
        mock_run.return_value = _run_fail("falló")
        result = buscar_en_google("algo")
        assert "no pude" in result.lower()

    def test_empty_query(self):
        assert "qué buscar" in buscar_en_google("  ").lower()


def args_ok(mock_run, needle: str) -> bool:
    """Helper: ¿`needle` está en el -Command que se le pasó a PowerShell?"""
    return needle in mock_run.call_args[0][0][-1]


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
