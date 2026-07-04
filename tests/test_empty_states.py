from app.ui.state import AppDataState, get_app_data_state


def test_no_data_state_when_everything_is_empty():
    assert get_app_data_state(holdings=[], transactions=[], cash_ledger=[], snapshots=[], fx_rate=1380) == AppDataState.NO_DATA


def test_sample_mode_state_takes_precedence():
    assert get_app_data_state(sample_mode=True, holdings=[{"ticker": "AAPL"}]) == AppDataState.SAMPLE_MODE


def test_partial_data_state_for_cash_only_or_unpriced_holdings():
    assert get_app_data_state(cash_ledger=[{"event_type": "deposit"}], fx_rate=1380) == AppDataState.PARTIAL_DATA
    assert get_app_data_state(holdings=[{"ticker": "AAPL"}], fx_rate=1380) == AppDataState.PARTIAL_DATA


def test_ready_state_when_holdings_have_price_and_fx():
    assert (
        get_app_data_state(
            holdings=[{"ticker": "AAPL", "current_price": 195}],
            transactions=[],
            cash_ledger=[],
            snapshots=[],
            fx_rate=1380,
        )
        == AppDataState.READY
    )


def test_error_state_takes_precedence_over_data():
    assert get_app_data_state(holdings=[{"ticker": "AAPL", "current_price": 195}], fx_rate=1380, error=RuntimeError("boom")) == AppDataState.ERROR_STATE
