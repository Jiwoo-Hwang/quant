import sys
from dataclasses import replace
from config import TradingConfig, OPENAI_API_KEY, ALPHA_VANTAGE_KEY
from market_data import get_market_data
from news_data import get_news_events
from strategy import determine_final_decision
from report import render_final_report


def get_ticker_input() -> str:
    """커맨드라인 argument 또는 사용자 입력으로 ticker를 받습니다."""
    if len(sys.argv) > 1:
        ticker = sys.argv[1].upper()
        print(f"📊 분석 종목: {ticker}")
        return ticker

    ticker = input("📊 분석할 종목 코드를 입력하세요 (기본값: TSLA): ").strip().upper()
    if not ticker:
        ticker = "TSLA"
    return ticker


def main() -> None:
    print("🚀 Running Improved AI Agent...")

    try:
        ticker = get_ticker_input()
        config = replace(TradingConfig(), ticker=ticker)

        data = get_market_data(config.ticker, config)
        if not data:
            raise RuntimeError("시장 데이터를 충분히 가져오지 못했습니다.")

        news = get_news_events(config.ticker, config)
        result = determine_final_decision(data, news, config)

        print()
        print(render_final_report(result))

    except Exception as e:
        print("\n[ERROR] 실행 중 오류가 발생했습니다:")
        print(str(e))


if __name__ == "__main__":
    main()