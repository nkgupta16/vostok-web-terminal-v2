# 🚀 Vostok Web Terminal v2
> **Professional-grade MOEX Quantitative Trading Dashboard**  
> A high-performance Streamlit application for advanced market analysis, volatility squeeze detection, and paper trading.

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **📈 Dashboard** | Quantitative Confidence Scoring (0-100%) with weighted RSI/BB/Volume/MACD signals |
| **💥 Squeeze** | Pre-pump volatility squeeze detection via BB Width percentile, OBV slope, ATR ratio |
| **💼 Portfolio** | Real-time portfolio with positions, P&L, Day P&L, and recent operations |
| **📅 Dividends** | Cross-references held tickers with upcoming dividends — Expected Payout & Yield % |
| **🎮 Sandbox** | T-Bank SandboxClient for paper trading — virtual deposits and BUY execution |
| **🧠 Strategy** | Equity Curve and Drawdown charts for "Dip" and "Squeeze" strategy backtests |

## 🏗️ Architecture

```
Vostok_Web_Terminal/
├── app.py                  # Main Streamlit UI & Navigation
├── services/
│   ├── auth.py             # Triple-Layer Credential System
│   ├── indicators.py       # Pure math engine (no Streamlit dependency)
│   ├── market.py           # T-Bank API & data fetching
│   ├── portfolio.py        # Dividend & Account logic + Sandbox
│   └── utils.py            # Shared utilities (retry, money helpers, timezone)
├── .streamlit/
│   └── config.toml         # Dark theme, layout settings
├── .devcontainer/
│   └── devcontainer.json   # VS Code Dev Container support
├── requirements.txt
├── .env.example
├── .gitignore
├── LICENSE                 # MIT License
└── README.md
```

## 🔑 Triple-Layer Credential System

The token is resolved with this priority:

1. **Manual Override** — paste into the sidebar password field
2. **Local `.env`** — `INVEST_TOKEN=your_token_here`
3. **Streamlit Cloud Secrets** — Dashboard → Settings → Secrets

### Account Selection

The brokerage account is resolved automatically:

1. **`INVEST_ACCOUNT_ID`** environment variable or Streamlit secret (if set)
2. **First brokerage account** found via the API (fallback)

## 🚀 Deployment

### Streamlit Community Cloud

1. Push to a GitHub repo (public or private)
2. Go to [share.streamlit.io](https://share.streamlit.io) → **New app**
3. Select your repo → branch: `master` → file: `app.py`
4. Add secrets in **Settings → Secrets**:

```toml
INVEST_TOKEN = "your_tbank_api_token_here"
# INVEST_ACCOUNT_ID = "optional_account_id"
```

> The T-Bank SDK installs automatically via `--extra-index-url` in `requirements.txt`.

### Local Development

```bash
# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac

# Install dependencies (includes T-Bank SDK via custom index)
pip install -r requirements.txt

# Configure token
copy .env.example .env
# Edit .env and add your INVEST_TOKEN

# Run
streamlit run app.py
```

Or use the convenience script on Windows:
```
start.bat
```

## 🎨 Theme

- **Layout:** Wide mode (forced via `set_page_config`)
- **Color Palette:** Electric Blue `#00e5ff` accent on dark `#0a0e12` background
- **Fonts:** Inter (UI) + JetBrains Mono (data/monospace)
- **Timezone:** All timestamps display in UTC+3 / Moscow Time (MSK)
- **Auto-Scan:** Toggle in sidebar with configurable intervals (10s–300s or custom)

## ⚠️ Safety

- **No real orders** — all execution buttons route to the Sandbox Service
- `indicators.py` has zero Streamlit imports — can be tested independently
- Token is never logged or displayed in the UI
- Account ID is resolved from environment, never hardcoded

## 📄 License

[MIT License](LICENSE) — see `LICENSE` file for details.
