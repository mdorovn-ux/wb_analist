from __future__ import annotations

from datetime import date

import pandas as pd

from wb_finance_analyst.services.numeric import to_number
from wb_finance_analyst.services.wb_api_client import WBApiClient

PROMOTION_BASE_URL = "https://advert-api.wildberries.ru"


class WBPromotionAPI:
    def __init__(self, token: str) -> None:
        self.client = WBApiClient(token=token, base_url=PROMOTION_BASE_URL)

    def get_ad_expenses(self, date_from: date, date_to: date) -> pd.DataFrame:
        data = self.client.get("/adv/v1/upd", params={"from": date_from.isoformat(), "to": date_to.isoformat()})
        return promotion_rows_to_dataframe(_as_list(data))

    def get_ad_fullstats(self, date_from: date, date_to: date) -> pd.DataFrame:
        data = self.client.get("/adv/v2/fullstats", params={"from": date_from.isoformat(), "to": date_to.isoformat()})
        return promotion_rows_to_dataframe(_as_list(data))


def promotion_rows_to_dataframe(rows: list[dict]) -> pd.DataFrame:
    result = []
    for row in rows:
        campaign_id = row.get("advertId") or row.get("advert_id") or row.get("id")
        campaign = row.get("campName") or row.get("name") or row.get("campaignName") or ""
        nm_id = row.get("nmId") or row.get("nm_id") or ""
        product = row.get("nmName") or row.get("product") or ""
        expense = row.get("sum") or row.get("expense") or row.get("cost") or row.get("updSum") or 0
        result.append(
            {
                "Дата": row.get("date") or row.get("updTime") or "",
                "Кампания": campaign,
                "ID кампании": campaign_id,
                "nmId": nm_id,
                "Товар": product,
                "Расход": to_number(expense),
                "Источник оплаты": row.get("paymentType") or row.get("source") or "",
                "Тип рекламы": row.get("type") or row.get("advertType") or "",
            }
        )
    return pd.DataFrame(result, columns=["Дата", "Кампания", "ID кампании", "nmId", "Товар", "Расход", "Источник оплаты", "Тип рекламы"])


def _as_list(data: dict | list) -> list[dict]:
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    for key in ("data", "rows", "items"):
        value = data.get(key)
        if isinstance(value, list):
            return [row for row in value if isinstance(row, dict)]
    return []
