import ast
import re
import subprocess
from pathlib import Path

import pytest

from build import main as build_installer, verifier_source

ROOT = Path(__file__).resolve().parents[1]
ENCODING = "utf-8"


def shell_functions():
    source = (ROOT / "install_cxh_fp.sh").read_text(encoding=ENCODING)
    return source.rsplit('\nmain "$@"', 1)[0]


def run_shell(body, tmp_path):
    script = tmp_path / "fixture.sh"
    script.write_text(shell_functions() + "\n" + body, encoding=ENCODING)
    return subprocess.run(
        ["bash", str(script)], text=True, capture_output=True, timeout=10
    )


def test_generated_installer_is_reproducible():
    before = (ROOT / "install_cxh_fp.sh").read_bytes()
    build_installer()
    assert (ROOT / "install_cxh_fp.sh").read_bytes() == before
    assert (
        subprocess.run(
            ["bash", "-n", str(ROOT / "install_cxh_fp.sh")], check=False
        ).returncode
        == 0
    )


@pytest.mark.parametrize("language", ["ru", "en"])
def test_preview_has_no_privileged_side_effects(language):
    result = subprocess.run(
        ["bash", str(ROOT / "install_cxh_fp.sh"), "--preview", "--language", language],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert "3.11.16" in result.stdout and "/opt/cxh-fp" in result.stdout
    assert not result.stderr


@pytest.mark.parametrize(
    "arguments", [["--language", "uk"], ["--language"], ["--unknown"]]
)
def test_invalid_arguments_stop(arguments):
    result = subprocess.run(
        ["bash", str(ROOT / "install_cxh_fp.sh"), *arguments],
        capture_output=True,
        timeout=5,
    )
    assert result.returncode == 2


def test_language_prompt_runs_before_platform_checks():
    result = subprocess.run(
        ["bash", str(ROOT / "install_cxh_fp.sh"), "--preview"],
        input="2\n",
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert result.stdout.index("English") < result.stdout.index("Ubuntu 22.04")


def test_existing_installation_preserves_data_and_finishes_setup(tmp_path):
    body = """
PROJECT_DIRECTORY="$PWD"
LANGUAGE=en
ensure_account() { printf 'account\\n'; }
stat() { printf 'coxerhub'; }
validate_python_prefix() { :; }
PYTHON_PREFIX="$PWD/python"
install_dependencies() { printf 'dependencies\\n'; }
configure_project() { printf 'setup\\n'; }
start_service() { printf 'start\\n'; }
resume_existing
"""
    (tmp_path / "main.py").write_text("pass\n", encoding=ENCODING)
    (tmp_path / "requirements.txt").write_text("", encoding=ENCODING)
    binary = tmp_path / "python/bin/python3.11"
    binary.parent.mkdir(parents=True)
    binary.touch(mode=0o755)
    environment = tmp_path / ".venv/bin/python"
    environment.parent.mkdir(parents=True)
    environment.touch(mode=0o755)
    marker = tmp_path / "plugins-private.txt"
    marker.write_text("preserved", encoding=ENCODING)
    result = run_shell("cd " + repr(str(tmp_path)) + "\n" + body, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "dependencies\n" in result.stdout and "setup\nstart\n" in result.stdout
    assert marker.read_text(encoding=ENCODING) == "preserved"


def test_existing_unrelated_directory_stops_without_starting(tmp_path):
    result = run_shell(
        "PROJECT_DIRECTORY="
        + repr(str(tmp_path))
        + "\nLANGUAGE=en\nstart_service() { printf 'UNEXPECTED'; }\nresume_existing\n",
        tmp_path,
    )
    assert result.returncode == 1
    assert "UNEXPECTED" not in result.stdout


def test_failed_dependency_install_never_reaches_setup_or_service(tmp_path):
    body = """
LANGUAGE=en
install_dependencies() { return 7; }
configure_project() { printf 'UNEXPECTED'; }
start_service() { printf 'UNEXPECTED'; }
install_dependencies
configure_project
start_service
"""
    result = run_shell(body, tmp_path)
    assert result.returncode == 7
    assert "UNEXPECTED" not in result.stdout


def test_new_service_restarts_and_waits_for_nonce_readiness(tmp_path):
    body = """
LANGUAGE=en
write_service() { printf 'unit\\n'; }
systemctl() { printf 'systemctl %s\\n' "$*"; }
check_ready() { printf 'ready\\n'; }
start_service
"""
    result = run_shell(body, tmp_path)
    assert result.returncode == 0, result.stderr
    assert (
        "unit\nsystemctl daemon-reload\nsystemctl enable cxh-fp.service\nsystemctl restart cxh-fp.service\n"
        in result.stdout
    )
    assert "ready\n" in result.stdout


def test_verifier_code_has_no_comments_docstrings_or_large_functions():
    tree = ast.parse(verifier_source())
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.end_lineno - node.lineno + 1 <= 30, node.name
            assert ast.get_docstring(node) is None
    assert len(verifier_source().splitlines()) < 1000


def test_service_keeps_bot_unprivileged_with_update_access():
    service = (ROOT / "cxh-fp.service").read_text(encoding=ENCODING)
    assert "User=coxerhub" in service and "Group=coxerhub" in service
    assert "ReadWritePaths=/opt/cxh-fp" in service and "NoNewPrivileges=true" in service
    assert (
        "ProtectSystem=strict" in service
        and "ExecStart=/opt/cxh-fp/.venv/bin/python /opt/cxh-fp/main.py" in service
    )


def test_bash_functions_stay_compact():
    source = (ROOT / "installer.sh.in").read_text(encoding=ENCODING)
    for match in re.finditer(
        r"^([a-z_]+)\(\) \{\n(.*?)^\}", source, re.MULTILINE | re.DOTALL
    ):
        assert len(match.group(0).splitlines()) <= 30, match.group(1)
