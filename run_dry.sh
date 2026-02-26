#!/usr/bin/env bash
# run_dry.sh — Safe full-loop test with no hardware.
# Run this any time to verify the pipeline without a connected printer.

echo ""
echo "======================================================"
echo "  🧪  agent_body_lab — Dry Run Test"
echo "======================================================"
echo ""

# Force DRY_RUN regardless of .env setting
export DRY_RUN=true

python3 pipeline.py
