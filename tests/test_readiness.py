import json
import os
from pathlib import Path

import pytest

from bootstrap import readiness

NONCE = "a1" * 16
ENCODING = "utf-8"


@pytest.fixture
def ready_tree(tmp_path):
    root = tmp_path / "project"
    health = root / "storage/updates/healthy.json"
    health.parent.mkdir(parents=True)
    health.write_text(json.dumps({"nonce": NONCE, "version": "1.1"}), encoding=ENCODING)
    proc = tmp_path / "proc"
    children = proc / "10/task/10/children"
    children.parent.mkdir(parents=True)
    children.write_text("11", encoding="ascii")
    environment = proc / "11/environ"
    environment.parent.mkdir(parents=True)
    environment.write_bytes(
        b"A=B\0CXH_UPDATE_HEALTH_NONCE=" + NONCE.encode("ascii") + b"\0"
    )
    return root, health, proc


def test_current_child_nonce_confirms_readiness(ready_tree):
    root, _, proc = ready_tree
    assert readiness.process_ready(root, "10", proc)


def test_stale_nonce_never_confirms_readiness(ready_tree):
    root, health, proc = ready_tree
    health.write_text(json.dumps({"nonce": "b2" * 16}), encoding=ENCODING)
    assert not readiness.process_ready(root, "10", proc)


def test_fifo_is_rejected_without_waiting_for_writer(ready_tree):
    root, health, proc = ready_tree
    health.unlink()
    os.mkfifo(health)
    with pytest.raises(ValueError):
        readiness.process_ready(root, "10", proc)


def test_leaf_symlink_is_rejected(ready_tree, tmp_path):
    root, health, proc = ready_tree
    destination = tmp_path / "external.json"
    health.rename(destination)
    health.symlink_to(destination)
    with pytest.raises(OSError):
        readiness.process_ready(root, "10", proc)


def test_parent_symlink_is_rejected(ready_tree, tmp_path):
    root, health, proc = ready_tree
    destination = tmp_path / "external-updates"
    health.parent.rename(destination)
    health.parent.symlink_to(destination, target_is_directory=True)
    with pytest.raises(OSError):
        readiness.process_ready(root, "10", proc)


def test_oversized_health_is_rejected(ready_tree):
    root, health, proc = ready_tree
    health.write_bytes(b" " * (readiness.HEALTH_LIMIT + 1))
    with pytest.raises(ValueError):
        readiness.process_ready(root, "10", proc)


@pytest.mark.parametrize(
    "nonce", [None, 12, [], "", "z" * 32, "A" * 32, "a" * 31, "a" * 33]
)
def test_nonce_type_and_format_are_required(ready_tree, nonce):
    root, health, proc = ready_tree
    health.write_text(json.dumps({"nonce": nonce}), encoding=ENCODING)
    with pytest.raises(ValueError):
        readiness.process_ready(root, "10", proc)


def test_environment_read_is_bounded(ready_tree):
    root, _, proc = ready_tree
    (proc / "11/environ").write_bytes(b"a" * (readiness.ENVIRONMENT_LIMIT + 1))
    with pytest.raises(ValueError):
        readiness.process_ready(root, "10", proc)


@pytest.mark.parametrize("pid", ["0", "../10", "10;command", "1" * 11])
def test_invalid_supervisor_pid_never_reads_files(ready_tree, pid):
    root, health, proc = ready_tree
    health.unlink()
    assert not readiness.process_ready(root, pid, proc)
