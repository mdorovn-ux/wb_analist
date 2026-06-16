from wb_finance_analyst.domain.models import ExternalExpense
from wb_finance_analyst.services.business_expenses import BusinessExpensesCalculator


def test_business_expenses_fixed_and_percent():
    df, total = BusinessExpensesCalculator().calculate(
        [
            ExternalExpense(name="Аренда", amount=100),
            ExternalExpense(name="Менеджер", amount=10, mode="percent_of_sales"),
        ],
        1000,
    )
    assert total == 200
    assert len(df) == 2
