#!/usr/bin/env bash
set -euo pipefail
source <(sed '$d' install_cxh_fp.sh)
LANGUAGE=en
source /etc/os-release
validate_distribution "$ID" "$VERSION_ID" "$PRETTY_NAME"
validate_private_paths
prepare_workspace
install_bootstrap_packages
download_release
install_python
validate_project_python
prepare_project
python_is_complete
cd "$PROJECT_DIRECTORY"
runuser -u "$SERVICE_USER" -- .venv/bin/python -c 'import sys, ssl, sqlite3, telebot, first_setup; assert sys.version_info[:3] == (3, 11, 16); print("Runtime imports passed")'
runuser -u "$SERVICE_USER" -- .venv/bin/python setup.py --check --language en
runuser -u "$SERVICE_USER" -- .venv/bin/python setup.py --preview --language en
runuser -u "$SERVICE_USER" -- .venv/bin/python main.py --help
write_service
printf 'Verified signed release, Python build, dependencies, setup CLI and service unit. Live authentication and service startup were not tested.\n'
