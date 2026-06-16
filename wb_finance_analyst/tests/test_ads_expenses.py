from wb_finance_analyst.services.wb_promotion_api import promotion_rows_to_dataframe


def test_promotion_rows_to_dataframe_sums_expenses():
    df = promotion_rows_to_dataframe([{"advertId": 1, "campName": "Search", "nmId": 2, "sum": "123,45"}])
    assert df.loc[0, "ID кампании"] == 1
    assert df["Расход"].sum() == 123.45
