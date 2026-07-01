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
