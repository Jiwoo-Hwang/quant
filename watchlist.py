from typing import Dict, List

WATCHLIST: Dict[str, List[str]] = {
    "AI_TECH":      ["NVDA", "MSFT", "META", "GOOGL", "AMZN", "AMD", "PLTR", "CRWD", "NET", "SNOW"],
    "SEMICONDUCTOR":["AVGO", "QCOM", "MU", "INTC", "AMAT", "TSM", "SMCI"],
    "EV_AUTO":      ["TSLA", "RIVN", "F", "GM", "LCID"],
    "BIOTECH":      ["LLY", "MRNA", "ABBV", "PFE", "AMGN"],
    "FINANCE":      ["JPM", "GS", "BAC", "MS", "V", "MA"],
    "ENERGY":       ["XOM", "CVX", "COP"],
    "DEFENSE":      ["LMT", "RTX", "BA"],
    "CONSUMER":     ["COST", "WMT", "TGT"],
}

ALL_TICKERS: List[str] = [ticker for tickers in WATCHLIST.values() for ticker in tickers]
