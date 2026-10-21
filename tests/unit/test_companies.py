from sec_fetcher.companies import load_all_companies, load_companies, load_cik_map, TICKERS


def test_load_all_companies_count():
    assert len(load_all_companies()) == 10443


def test_load_all_companies_sorted_by_ticker():
    tickers = [c.ticker for c in load_all_companies()]
    assert tickers == sorted(tickers)


def test_load_all_companies_fields():
    index = {c.ticker: c for c in load_all_companies()}
    aapl = index["AAPL"]
    assert aapl.cik == 320193
    assert "Apple" in aapl.title


def test_load_companies_returns_target_tickers_in_order():
    assert [c.ticker for c in load_companies()] == TICKERS


def test_load_cik_map():
    cik_map = load_cik_map()
    assert cik_map == {
        "AAPL":  320193,
        "META":  1326801,
        "GOOGL": 1652044,
        "AMZN":  1018724,
        "NFLX":  1065280,
        "GS":    886982,
    }
