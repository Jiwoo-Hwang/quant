from config import CONFIG
from market_data import get_market_data
from news_data import get_news_events
from strategy import determine_final_decision
from report import render_final_report


def main() -> None:
    print("🚀 Running Improved AI Agent...")

    try:
        data = get_market_data(CONFIG.ticker, CONFIG)
        if not data:
            raise RuntimeError("시장 데이터를 충분히 가져오지 못했습니다.")

        news = get_news_events(CONFIG.ticker, CONFIG)
        result = determine_final_decision(data, news, CONFIG)

        print()
        print(render_final_report(result))

    except Exception as e:
        print("\n[ERROR] 실행 중 오류가 발생했습니다:")
        print(str(e))


if __name__ == "__main__":
    main()