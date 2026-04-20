#!/bin/bash
# Install T-Bank SDK from custom PyPI index (required for Streamlit Cloud)
set -euo pipefail

echo "Installing T-Bank Invest SDK..."
pip install t-tech-investments \
    --index-url https://opensource.tbank.ru/api/v4/projects/238/packages/pypi/simple \
    || { echo "ERROR: Failed to install T-Bank SDK"; exit 1; }

echo "T-Bank SDK installed successfully."
