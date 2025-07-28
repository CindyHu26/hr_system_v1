# services/performance_bonus_logic.py
import pandas as pd
from . import performance_bonus_scraper as scraper
from db import queries_attendance as q_att
from db import queries_performance_bonus as q_perf
from utils.helpers import get_monthly_dates

def fetch_target_count(username, password, year, month):
    """
    步驟一：僅負責呼叫爬蟲獲取目標人數。
    """
    start_date, end_date = get_monthly_dates(year, month)
    target_count = scraper.fetch_performance_count(username, password, start_date, end_date)
    return target_count

def get_eligible_employees(conn, year, month):
    """
    步驟二：查詢指定月份有出勤紀錄的員工。
    """
    attendance_df = q_att.get_attendance_by_month(conn, year, month)
    if attendance_df.empty:
        return pd.DataFrame()
    
    # 取得不重複的員工ID、編號和姓名
    eligible_employees_df = attendance_df[['employee_id', 'hr_code', 'name_ch']].drop_duplicates().reset_index(drop=True)
    return eligible_employees_df

def save_final_bonuses(conn, year, month, final_distribution_df):
    """
    步驟三：將最終確認（可能已被手動修改）的獎金分配 DataFrame 存入資料庫。
    """
    if final_distribution_df.empty:
        return 0
    
    # 函式 q_perf.save_performance_bonuses 已包含「先刪後插」邏輯，直接呼叫即可
    saved_count = q_perf.save_performance_bonuses(conn, year, month, final_distribution_df)
    return saved_count