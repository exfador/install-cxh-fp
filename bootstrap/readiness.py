import json
import os
import re
import stat
import sys
from pathlib import Path

HEALTH_COMPONENTS = ("storage", "updates")
HEALTH_FILENAME = "healthy.json"
HEALTH_LIMIT = 1024
CHILDREN_LIMIT = 1024
ENVIRONMENT_LIMIT = 128 * 1024
NONCE_PATTERN = r"[0-9a-f]{32}"
PID_PATTERN = r"[1-9][0-9]{0,9}"
CHILD_LIMIT = 16
HEALTH_ENVIRONMENT_PREFIX = b"CXH_UPDATE_HEALTH_NONCE="
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK


def bounded_descriptor(fd, maximum):
    metadata = os.fstat(fd)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum:
        raise ValueError("Invalid readiness file")
    data = os.read(fd, maximum + 1)
    if len(data) > maximum:
        raise ValueError("Readiness file is too large")
    return data


def private_health(root):
    descriptors = []
    try:
        descriptors.append(os.open(root, DIRECTORY_FLAGS))
        for component in HEALTH_COMPONENTS:
            descriptors.append(
                os.open(component, DIRECTORY_FLAGS, dir_fd=descriptors[-1])
            )
        descriptors.append(os.open(HEALTH_FILENAME, FILE_FLAGS, dir_fd=descriptors[-1]))
        health = json.loads(bounded_descriptor(descriptors[-1], HEALTH_LIMIT))
        nonce = health.get("nonce") if type(health) is dict else None
        if (
            type(nonce) is not str
            or re.fullmatch(NONCE_PATTERN, nonce, re.ASCII) is None
        ):
            raise ValueError("Invalid readiness nonce")
        return nonce
    finally:
        for fd in reversed(descriptors):
            os.close(fd)


def proc_file(path, maximum):
    fd = os.open(path, FILE_FLAGS)
    try:
        return bounded_descriptor(fd, maximum)
    finally:
        os.close(fd)


def process_ready(root, supervisor, proc_root=Path("/proc")):
    if re.fullmatch(PID_PATTERN, supervisor, re.ASCII) is None:
        return False
    nonce = private_health(root)
    children_path = proc_root / supervisor / "task" / supervisor / "children"
    children = proc_file(children_path, CHILDREN_LIMIT).decode("ascii").split()
    if len(children) > CHILD_LIMIT:
        return False
    expected = HEALTH_ENVIRONMENT_PREFIX + nonce.encode("ascii")
    for child in children:
        if re.fullmatch(PID_PATTERN, child, re.ASCII) is None:
            return False
        environment = proc_file(proc_root / child / "environ", ENVIRONMENT_LIMIT)
        if expected in environment.split(b"\0"):
            return True
    return False


def main():
    try:
        ready = process_ready(Path(sys.argv[1]), sys.argv[2])
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        ready = False
    raise SystemExit(not ready)


if __name__ == "__main__":
    main()
