from app.collectors.sec_13f import parse_13f_info_table_for_tests


def test_parse_13f_info_table_maps_uber_and_amount():
    xml = """
    <informationTable>
      <infoTable>
        <nameOfIssuer>UBER TECHNOLOGIES INC</nameOfIssuer>
        <titleOfClass>COM</titleOfClass>
        <cusip>90353T100</cusip>
        <value>2150000</value>
        <shrsOrPrnAmt><sshPrnamt>30000000</sshPrnamt><sshPrnamtType>SH</sshPrnamtType></shrsOrPrnAmt>
      </infoTable>
    </informationTable>
    """
    rows = parse_13f_info_table_for_tests(xml)
    assert rows
    row = rows[0]
    assert row["ticker"] == "UBER"
    assert row["source"] == "INSTITUTIONAL_13F"
    assert row["action"] == "HOLDING_13F"
    assert row["amount_usd"] == 2_150_000_000
    assert row["trade_date"] == "2026-03-31"


def test_repair_cached_13f_amounts_from_raw_json(tmp_path):
    from app.config import settings
    from app.db import init_db, normalize_institutional_13f_amounts, upsert_trades, get_conn

    old_db = settings.database_path
    object.__setattr__(settings, "database_path", tmp_path / "whale.db")
    try:
        init_db()
        upsert_trades([
            {
                "source_id": "13F:test:googl",
                "ticker": "GOOGL",
                "company_name": "ALPHABET INC",
                "cik": "1656456",
                "accession_number": "x",
                "filing_url": "https://example.com/infotable.xml",
                "whale_name": "David Tepper",
                "whale_category": "Institutional 13F",
                "insider_role": "Appaloosa LP",
                "action": "HOLDING_13F",
                "transaction_code": "13F",
                # Old cached bug: should be $497.044M, not $497.044B.
                "amount_usd": 497_044_000_000,
                "shares": 1_732_700,
                "price": None,
                "trade_date": "2026-03-31",
                "filing_date": "2026-05-15",
                "source": "INSTITUTIONAL_13F",
                "raw_json": '{"value_reported":497044,"value_unit":"thousands_usd"}',
            }
        ])
        assert normalize_institutional_13f_amounts() == 1
        with get_conn() as conn:
            amount = conn.execute("SELECT amount_usd FROM trades WHERE source_id='13F:test:googl'").fetchone()[0]
        assert amount == 497_044_000
    finally:
        object.__setattr__(settings, "database_path", old_db)
