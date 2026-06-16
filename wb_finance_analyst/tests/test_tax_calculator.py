from wb_finance_analyst.domain.models import TaxSettings
from wb_finance_analyst.services.tax_calculator import TaxCalculator


def test_tax_calculator_usn_and_nds():
    df, total = TaxCalculator().calculate(TaxSettings(mode="usn_nds", usn_rate=6, nds_rate=20), 1000)
    assert total == 260
    assert set(df["Тип налога"]) == {"УСН", "НДС"}


def test_tax_calculator_manual():
    _, total = TaxCalculator().calculate(TaxSettings(mode="manual", manual_amount=123.45), 1000)
    assert total == 123.45
