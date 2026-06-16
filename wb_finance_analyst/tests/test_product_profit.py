import pandas as pd

from wb_finance_analyst.domain.models import ColumnMap, CostItem
from wb_finance_analyst.services.product_profit_calculator import ProductProfitCalculator


def test_product_profit_uses_costs_and_net_quantity():
    df = pd.DataFrame(
        [
            {"Тип документа": "Продажа", "Название": "A", "Кол-во": 2, "К перечислению": 1000},
            {"Тип документа": "Возврат", "Название": "A", "Кол-во": 1, "К перечислению": -400},
        ]
    )
    mapping = ColumnMap(doc_type="Тип документа", product_name="Название", quantity="Кол-во", seller_transfer="К перечислению")
    table, warnings = ProductProfitCalculator().calculate(df, mapping, {"a": CostItem(product="A", cost=100, packaging=10)})
    assert not warnings
    assert table.loc[0, "Чистое количество"] == 1
    assert table.loc[0, "Себестоимость"] == 100
    assert table.loc[0, "Упаковка"] == 10
    assert table.loc[0, "Чистая прибыль"] == 490
