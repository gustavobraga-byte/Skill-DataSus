#!/usr/bin/env bash
# OpenDataSUS Skill — Installer
# No external dependencies required. Python 3 stdlib only.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SKILL_DIR"

echo "=========================================="
echo " OpenDataSUS — Dados Abertos do SUS"
echo " Skill Installer"
echo "=========================================="
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "[ERROR] python3 not found. Install Python 3.8+ first."
    exit 1
fi

PY_VERSION=$(python3 --version 2>&1)
echo "  ✓ Python: $PY_VERSION"

# Verify opendatasus.py
if [ ! -f "opendatasus.py" ]; then
    echo "[ERROR] opendatasus.py not found in $SKILL_DIR"
    exit 1
fi

# Make executable
chmod +x opendatasus.py

# Verify imports (all stdlib)
echo "  ✓ Verifying imports..."
python3 -c "
import csv, io, json, re, sys, time, urllib.request, urllib.error, zipfile, argparse
from collections import defaultdict
print('  ✓ All imports OK (stdlib only)')
" 2>&1

echo ""
echo "=========================================="
echo " Installation complete!"
echo "=========================================="
echo ""
echo " Skill location: $SKILL_DIR"
echo ""
echo " Quick test:"
echo "   python3 opendatasus.py list"
echo "   python3 opendatasus.py info srag-2019-a-2026"
echo "   python3 opendatasus.py query srag-2019-a-2026 --sample"
echo ""
echo " To use as an AI agent skill:"
echo "   - Claude Code:  copy SKILL.md to CLAUDE.md"
echo "   - Cursor:       copy SKILL.md to .cursor/rules/"
echo "   - OpenCode:     add to opencode.json skills list"
echo "   - Aider:        use --read SKILL.md"
echo "   - Manual:       'cat SKILL.md | pbcopy' and paste to agent"
echo ""
