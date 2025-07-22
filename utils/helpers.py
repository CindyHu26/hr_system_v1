# utils/helpers.py
import pandas as pd
from calendar import monthrange
from datetime import datetime

def get_monthly_dates(year, month):
    """
    根據給定的年和月，回傳該月的第一天和最後一天的字串。

    Args:
        year (int): 年份。
        month (int): 月份。

    Returns:
        tuple[str, str]: (第一天字串, 最後一天字串)，格式為 'YYYY-MM-DD'。
    """
    first_day_str = f"{year}-{month:02d}-01"
    _, last_day_num = monthrange(year, month)
    last_day_str = f"{year}-{month:02d}-{last_day_num}"
    return first_day_str, last_day_str

def to_date(date_string):
    """
    安全地將日期字串轉換為 date 物件，處理 None 或無效格式。
    """
    if date_string and pd.notna(date_string):
        try:
            return pd.to_datetime(date_string).date()
        except (ValueError, TypeError):
            return None
    return None

# 未來可以新增更多通用函式，例如：
# def format_currency(amount):
#     """將數字格式化為貨幣字串"""
#     return f"NT$ {amount:,.0f}"

