import ast
import re
import subprocess
import sys
import zipfile
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
install_python() { printf 'python\\n'; }
runuser() { printf 'venv\\n'; }
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
    assert "python\nvenv\n" in result.stdout
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


PYTHON_BUILD_FIXTURE = """
cd __WORK_DIRECTORY__
LANGUAGE=en
WORK_DIRECTORY="$PWD"
PYTHON_PREFIX="$PWD/prefix"
timeout() { shift; "$@"; }
validate_python_prefix() { printf 'ownership\\n'; }
download() { printf 'download\\n'; }
sha256sum() { cat >/dev/null; printf 'checksum\\n'; }
tar() { printf 'extract\\n'; }
install() { printf 'directories\\n'; }
build_jobs() { printf '1'; }
make() {
    printf 'make %s\\n' "$*"
    if [[ "$1" == 'altinstall' ]]; then
        printf '#!/bin/bash\\nexit 0\\n' > "$PYTHON_PREFIX/bin/python3.11"
    fi
}
install_python
"""


def python_build_fixture(tmp_path, complete=False):
    binary = tmp_path / "prefix/bin/python3.11"
    binary.parent.mkdir(parents=True)
    binary.write_text(
        "#!/bin/bash\nexit " + ("0" if complete else "1") + "\n", encoding=ENCODING
    )
    binary.chmod(0o755)
    build = tmp_path / "Python-3.11.16"
    build.mkdir()
    configure = build / "configure"
    configure.write_text("#!/bin/bash\nprintf 'configure\\n'\n", encoding=ENCODING)
    configure.chmod(0o755)
    return PYTHON_BUILD_FIXTURE.replace("__WORK_DIRECTORY__", repr(str(tmp_path)))


def test_incomplete_executable_python_is_rebuilt_without_touching_private_data(
    tmp_path,
):
    marker = tmp_path / "private.txt"
    marker.write_text("preserved", encoding=ENCODING)
    result = run_shell(python_build_fixture(tmp_path), tmp_path)
    assert result.returncode == 0, result.stderr
    assert "download\nchecksum\nextract\n" in result.stdout
    assert "make -j 1\nmake altinstall\n" in result.stdout
    assert marker.read_text(encoding=ENCODING) == "preserved"


def test_complete_python_skips_download_and_rebuild(tmp_path):
    result = run_shell(python_build_fixture(tmp_path, complete=True), tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout == "ownership\n"


def test_failed_rebuild_cannot_continue_to_venv_or_service(tmp_path):
    source = python_build_fixture(tmp_path)
    source = source.replace(
        "install_python\n",
        "make() { return 9; }\ninstall_python\nprintf 'UNEXPECTED'\n",
    )
    result = run_shell(source, tmp_path)
    assert result.returncode == 9
    assert "UNEXPECTED" not in result.stdout


def test_successful_make_with_incomplete_python_still_stops(tmp_path):
    source = python_build_fixture(tmp_path)
    source = source.replace(
        "install_python\n",
        "make() { return 0; }\ninstall_python\nprintf 'UNEXPECTED'\n",
    )
    result = run_shell(source, tmp_path)
    assert result.returncode == 1
    assert "Python installation is incomplete" in result.stderr
    assert "UNEXPECTED" not in result.stdout


def test_python_probe_is_isolated_and_checks_version_and_stdlib():
    source = (ROOT / "installer.sh.in").read_text(encoding=ENCODING)
    assert '-I -c "$PYTHON_PROBE" "$PYTHON_VERSION"' in source
    for module in ("ensurepip", "sqlite3", "ssl", "venv", "zipfile"):
        assert f"import {module}" in source
    assert "sys.version_info[:3]" in source and "archive.testzip()" in source


def bootstrap_probe(tmp_path, packages, corrupt=False):
    bundle = tmp_path / "_bundled"
    bundle.mkdir()
    for package in packages:
        wheel = bundle / f"{package}-1.0.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr(f"{package}/__init__.py", "ready")
        if corrupt and package == "setuptools":
            wheel.write_bytes(wheel.read_bytes().replace(b"ready", b"wrong"))
    source = (ROOT / "installer.sh.in").read_text(encoding=ENCODING)
    probe = re.search(r"PYTHON_PROBE='(.*?)'\n", source, re.DOTALL).group(1)
    prelude = "import sys, types\nmodule = types.ModuleType('ensurepip')\n"
    prelude += f"module.__file__ = {str(tmp_path / '__init__.py')!r}\n"
    prelude += "module.version = lambda: '1.0'\nsys.modules['ensurepip'] = module\n"
    version = ".".join(map(str, sys.version_info[:3]))
    return subprocess.run(
        [sys.executable, "-I", "-c", prelude + probe, version],
        capture_output=True,
        timeout=5,
    )


@pytest.mark.parametrize(
    "packages, corrupt, expected",
    [
        (("pip", "setuptools"), False, 0),
        (("pip",), False, 1),
        (("setuptools",), False, 1),
        (("pip", "setuptools"), True, 1),
    ],
)
def test_real_probe_requires_both_valid_bootstrap_wheels(
    tmp_path, packages, corrupt, expected
):
    result = bootstrap_probe(tmp_path, packages, corrupt)
    assert result.returncode == expected
