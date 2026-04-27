#!/usr/bin/env bash
# Install claude-local and its dependencies into a virtual environment.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

echo "==> Creating virtual environment at $VENV_DIR"
python3 -m venv "$VENV_DIR"

echo "==> Installing dependencies"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -e "$SCRIPT_DIR"

echo ""
echo "Done! To use claude-local:"
echo ""
echo "  1. Activate the venv (optional but convenient):"
echo "       source $VENV_DIR/bin/activate"
echo ""
echo "  2. Set your API key:"
echo "       export ANTHROPIC_API_KEY=sk-ant-..."
echo ""
echo "  3. Run:"
echo "       claude-local [directory] [--proxy http://proxy:8080]"
echo ""
echo "  Or without activating the venv:"
echo "       $VENV_DIR/bin/claude-local"
echo ""
