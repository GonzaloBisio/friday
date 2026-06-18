"""Tests para friday.agent.actions.pc_actions — acciones concretas de PC."""

from unittest.mock import patch, MagicMock
from pathlib import Path

import pytest

from friday.agent.actions.pc_actions import (
    abrir_app,
    info_sistema,
    leer_archivo,
    listar_directorio,
    listar_procesos,
)


class TestAbrirApp:
    @patch("friday.agent.actions.pc_actions.subprocess.Popen")
    def test_opens_app(self, mock_popen):
        result = abrir_app("notepad")
        assert "notepad" in result
        assert "abierta" in result.lower()
        mock_popen.assert_called_once()

    @patch("friday.agent.actions.pc_actions.subprocess.Popen", side_effect=OSError("not found"))
    def test_handles_error(self, mock_popen):
        result = abrir_app("inexistente")
        assert "no pude" in result.lower()


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
