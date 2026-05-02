Telegram Bot — Claude AI Chat + Crypto Trade Alerts
=====================================================
Features:
  - Chat with Claude AI directly from Telegram
  - Automatic crypto price scanning every 5 minutes
  - Trade alerts sent to your Telegram when conditions are met
  - Commands: /price, /scan, /status, /help

Install:
  pip install pytelegrambotapi anthropic requests schedule

Environment variables to set in Railway:
  TELEGRAM_TOKEN   = your bot token
  TELEGRAM_CHAT_ID = your personal chat ID
  ANTHROPIC_API_KEY = your Claude API key
"""

import os
import time
import threading
import logging
import requests
import schedule
from datetime import datetime

import telebot
import anthropic

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("bot.log")],
)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════════
#  CONFIG  — set these as environment variables in Railway
# ══════════════════════════════════════════════════════════════════════════
TELEGRAM_TOKEN   = os.getenv("TELEGRAM_TOKEN", "8760960206:AAHFpgLemXMEz_jhwa6clSBgwJhKPwvBcsI")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8651075661")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Coins to watch
WATCHLIST = ["BTC", "ETH", "SOL", "LINK"]

# Alert thresholds
RSI_BUY_THRESHOLD  = 40   # Alert when RSI drops below this (oversold)
RSI_SELL_THRESHOLD = 65   # Alert when RSI rises above this (overbought)
SCAN_INTERVAL_MIN  = 5    # How often to scan (minutes)

# ══════════════════════════════════════════════════════════════════════════
#  SETUP
# ══════════════════════════════════════════════════════════════════════════
bot    = telebot.TeleBot(TELEGRAM_TOKEN)
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Store conversation history per user for Claude context
conversation_history = {}


# ══════════════════════════════════════════════════════════════════════════
#  MARKET DATA  (free CoinGecko API — no key needed)
# ══════════════════════════════════════════════════════════════════════════
COIN_IDS = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "LINK": "chainlink",
}

def get_price(symbol: str) -> dict:
    """Fetch current price and 24h change from CoinGecko."""
    coin_id = COIN_IDS.get(symbol.upper())
    if not coin_id:
        return {}
    try:
        url = f"https://api.coingecko.com/api/v3/simple/price"
        params = {
            "ids": coin_id,
            "vs_currencies": "usd",
            "include_24hr_change": "true",
            "include_24hr_vol": "true",
        }
        r = requests.get(url, params=params, timeout=10)
        data = r.json().get(coin_id, {})
        return {
            "symbol":  symbol.upper(),
            "price":   data.get("usd", 0),
            "change":  data.get("usd_24h_change", 0),
            "volume":  data.get("usd_24h_vol", 0),
        }
    except Exception as e:
        log.error(f"Price fetch error for {symbol}: {e}")
        return {}


def get_rsi(symbol: str, period: int = 14) -> float:
    """Calculate RSI using daily closes from CoinGecko."""
    coin_id = COIN_IDS.get(symbol.upper())
    if not coin_id:
        return 50.0
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"
        params = {"vs_currency": "usd", "days": 30, "interval": "daily"}
        r = requests.get(url, params=params, timeout=10)
        prices = [p[1] for p in r.json().get("prices", [])]
        if len(prices) < period + 1:
            return 50.0

        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains  = [max(d, 0) for d in deltas]
        losses = [abs(min(d, 0)) for d in deltas]

        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        if avg_loss == 0:
            return 100.0
        rs  = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
        return round(rsi, 1)
    except Exception as e:
        log.error(f"RSI error for {symbol}: {e}")
        return 50.0
