import sys
from unittest.mock import patch, MagicMock
import runpy
import os
import pytest
from vizscan.cli import (
    main,
)

# --- PES HYBRID COVERAGE ---


class MockArgsExtended:
    def __init__(self, enable_dynamic=False, duration=5, fps=60, score_quality=False):
        self.enable_dynamic = enable_dynamic
        self.duration = duration
        self.fps = fps
        self.score_quality = score_quality
        self.path = ""
        self.recursive = False
        self.help_scoring = False
        self.output = ""


def test_hybrid_cli_help(capsys):
    with patch.object(sys, "argv", ["vizscan/cli.py", "--help"]):
        with pytest.raises(SystemExit):
            main()
    captured = capsys.readouterr()
    assert "usage:" in captured.out


def test_hybrid_cli_no_args(capsys):
    with patch.object(sys, "argv", ["vizscan/cli.py"]):
        with pytest.raises(SystemExit):
            main()
    captured = capsys.readouterr()
    assert "usage:" in captured.out


def test_hybrid_cli_scoring(capsys):
    with patch.object(sys, "argv", ["vizscan/cli.py", "--help-scoring"]):
        with pytest.raises(SystemExit):
            main()
    captured = capsys.readouterr()
    assert "pes:InverterStrobe" in captured.out


def test_hybrid_cli_file(tmp_path, capsys):
    p = tmp_path / "test.milk"
    p.write_text("ob_r = 0.5;")
    with patch.object(sys, "argv", ["vizscan/cli.py", str(p)]):
        main()
    captured = capsys.readouterr()
    assert "Scanning 1 files..." in captured.out
    assert "[PASS] test.milk" in captured.out


def test_hybrid_cli_dir_recursive(tmp_path, capsys):
    d = tmp_path / "subdir"
    d.mkdir()
    p = d / "test.milk"
    p.write_text("ob_r = 0.5;")
    with patch.object(sys, "argv", ["vizscan/cli.py", str(tmp_path), "--recursive"]):
        main()
    captured = capsys.readouterr()
    assert "Scanning 1 files..." in captured.out


def test_hybrid_cli_dir_flat(tmp_path, capsys):
    p = tmp_path / "test.milk"
    p.write_text("ob_r = 0.5;")
    with patch.object(sys, "argv", ["vizscan/cli.py", str(tmp_path)]):
        main()
    captured = capsys.readouterr()
    assert "Scanning 1 files..." in captured.out


def test_hybrid_cli_score_quality(tmp_path, capsys):
    p = tmp_path / "test.milk"
    p.write_text("ob_r = 0.5;")

    with patch.object(sys, "argv", ["vizscan/cli.py", str(p), "--score-quality"]):
        runpy.run_module("vizscan.cli", run_name="__main__")
    captured = capsys.readouterr()
    assert "Quality (Static)" in captured.out


def test_hybrid_main_execution(tmp_path, capsys):
    p = tmp_path / "test.milk"
    p.write_text("ob_r = 0.5;")

    with patch.object(sys, "argv", ["vizscan/cli.py", str(p)]):
        runpy.run_module("vizscan.cli", run_name="__main__")
    captured = capsys.readouterr()
    assert "[PASS]" in captured.out


def test_hybrid_main_invalid_file(capsys):
    with patch.object(sys, "argv", ["vizscan/cli.py", "nonexistent.milk"]):
        runpy.run_module("vizscan.cli", run_name="__main__")
    captured = capsys.readouterr()
    assert "Scanning 0 files..." in captured.out
