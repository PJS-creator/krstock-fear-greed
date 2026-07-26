import json

from portfolio.meta_strategy_sources import (
    merge_series,
    parse_fred_series_csv,
    parse_tiingo_adjusted_prices,
)


def test_tiingo_parser_uses_adjusted_close():
    payload = json.dumps(
        [
            {
                "date": "2026-07-24T00:00:00.000Z",
                "close": 600.0,
                "adjClose": 598.25,
            }
        ]
    )

    points = parse_tiingo_adjusted_prices(payload)

    assert points[0].value == 598.25
    assert points[0].as_of_date.isoformat() == "2026-07-24"


def test_fred_parser_accepts_observation_date_and_missing_values():
    payload = "observation_date,WALCL,WDTGAL\n2026-07-22,7000000,.\n2026-07-23,.,500000\n"

    parsed = parse_fred_series_csv(payload)

    assert parsed["WALCL"][0].value == 7000000.0
    assert parsed["WDTGAL"][0].value == 500000.0


def test_current_fred_values_win_when_splicing_archive():
    historical = parse_fred_series_csv(
        "DATE,BAMLH0A0HYM2\n2026-07-20,3.1\n2026-07-21,3.2\n"
    )["BAMLH0A0HYM2"]
    current = parse_fred_series_csv(
        "DATE,BAMLH0A0HYM2\n2026-07-21,3.25\n"
    )["BAMLH0A0HYM2"]

    merged = merge_series(historical, current)

    assert [point.value for point in merged] == [3.1, 3.25]
