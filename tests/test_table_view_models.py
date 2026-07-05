from app.ui.holdings import short_quote_status_label
from app.ui.performance import MONTHLY_BASE_COLUMNS, SYMBOL_BASE_COLUMNS, SYMBOL_DETAIL_COLUMNS
from app.ui.rebalancing import RESULT_BASE_COLUMNS, RESULT_DETAIL_COLUMNS


def test_rebalancing_result_defaults_to_compact_columns():
    assert RESULT_BASE_COLUMNS == ["자산", "현재 비중", "목표 비중", "차이 금액", "조정 수량", "조정 방향", "데이터 상태"]
    assert "현재 평가액" in RESULT_DETAIL_COLUMNS
    assert "목표 평가액" in RESULT_DETAIL_COLUMNS
    assert "예상 조정 금액" in RESULT_DETAIL_COLUMNS


def test_performance_tables_have_summary_and_detail_columns():
    assert SYMBOL_BASE_COLUMNS == ["종목", "보유수량", "현재가", "미실현손익", "실현손익", "총손익"]
    assert "평균단가" in SYMBOL_DETAIL_COLUMNS
    assert "환율효과" in SYMBOL_DETAIL_COLUMNS
    assert "월" in MONTHLY_BASE_COLUMNS
    assert "월 손익" in MONTHLY_BASE_COLUMNS


def test_quote_status_labels_are_shortened_for_table_display():
    assert short_quote_status_label("정상_최근종가") == "최근종가"
    assert short_quote_status_label("이전저장값사용") == "이전값"
