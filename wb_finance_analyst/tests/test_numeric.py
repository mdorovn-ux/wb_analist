from wb_finance_analyst.services.numeric import to_number


def test_to_number_handles_russian_formats():
    assert to_number("1 234,56") == 1234.56
    assert to_number("−10,5") == -10.5
    assert to_number(None) == 0
    assert to_number("abc") == 0
