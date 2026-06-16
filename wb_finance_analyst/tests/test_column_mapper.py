import pandas as pd

from wb_finance_analyst.services.column_mapper import ColumnMapper


def test_column_mapper_detects_wb_columns():
    df = pd.DataFrame(
        columns=[
            "Тип документа",
            "Обоснование для оплаты",
            "Название",
            "К перечислению Продавцу за реализованный Товар",
            "Услуги по доставке товара покупателю",
            "Хранение",
        ]
    )
    mapping = ColumnMapper().map_columns(df.columns)
    assert mapping.doc_type == "Тип документа"
    assert mapping.payment_reason == "Обоснование для оплаты"
    assert mapping.product_name == "Название"
    assert mapping.seller_transfer == "К перечислению Продавцу за реализованный Товар"
    assert mapping.logistics == "Услуги по доставке товара покупателю"
