#!/usr/bin/env bash
# One-time setup: creates ./.venv, installs local markitdown + converters + PyQt6.
set -e
cd "$(dirname "$0")"

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
  .venv/bin/python -m pip install -U pip
fi

.venv/bin/python -m pip install -e "packages/markitdown[docx,xlsx,xls,pptx,pdf,outlook]" PyQt6
echo
echo "Setup complete. Run the GUI with: ./run_gui.sh"
