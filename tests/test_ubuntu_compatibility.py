import ast
import sys
from pathlib import Path

import pytest

from build import verifier_source
from bootstrap.archive import release_path
from tests.test_installer import run_shell

SUPPORTED_VERSIONS = ("20.04", "22.04", "24.04")
UNSUPPORTED_DISTRIBUTIONS = (("ubuntu", "18.04"), ("debian", "12"))


@pytest.mark.parametrize("version", SUPPORTED_VERSIONS)
def test_supported_distribution_continues(version, tmp_path):
    result = run_shell(
        f'LANGUAGE=en\nvalidate_distribution ubuntu {version} "Ubuntu {version}"\nprintf CONTINUED',
        tmp_path,
    )
    assert result.returncode == 0
    assert f"Detected system: Ubuntu {version}." in result.stdout
    assert "CONTINUED" in result.stdout


@pytest.mark.parametrize("distribution, version", UNSUPPORTED_DISTRIBUTIONS)
def test_unsupported_distribution_explains_stop(distribution, version, tmp_path):
    result = run_shell(
        f'LANGUAGE=en\nvalidate_distribution {distribution} {version} "{distribution} {version}"\nprintf UNEXPECTED',
        tmp_path,
    )
    assert result.returncode == 1
    assert f"{distribution} {version} is unsupported" in result.stderr
    assert "Error: Installation stopped:" in result.stderr
    assert "The system was not changed" in result.stderr
    assert "UNEXPECTED" not in result.stdout


def test_embedded_verifier_accepts_python_38_syntax():
    ast.parse(verifier_source(), feature_version=8)


def test_directory_path_retains_canonical_validation():
    assert release_path("app/", directory=True).as_posix() == "app"
    with pytest.raises(ValueError):
        release_path("app//", directory=True)


def syntax_check(tmp_path, source):
    code = tmp_path / "source/main.py"
    code.parent.mkdir()
    code.write_text(source, encoding="utf-8")
    executable = tmp_path / "python/bin/python3.11"
    executable.parent.mkdir(parents=True)
    executable.symlink_to(sys.executable)
    return run_shell(
        f'LANGUAGE=en\nWORK_DIRECTORY="{tmp_path}"\nPYTHON_PREFIX="{tmp_path}/python"\nvalidate_project_python\nprintf CONTINUED',
        tmp_path,
    )


def test_release_syntax_checked_with_project_interpreter(tmp_path):
    result = syntax_check(tmp_path, "value = 1\n")
    assert result.returncode == 0
    assert "CONTINUED" in result.stdout


def test_invalid_release_syntax_stops_before_setup(tmp_path):
    result = syntax_check(tmp_path, "def broken(:\n")
    assert result.returncode == 1
    assert "Release code failed Python 3.11 validation" in result.stderr
    assert "CONTINUED" not in result.stdout
