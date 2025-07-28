# services/performance_bonus_logic.py
import pandas as pd
from . import performance_bonus_scraper as scraper
from db import queries_attendance as q_att
from db import queries_performance_bonus as q_perf
from utils.helpers import get_monthly_dates

def calculate_and_save_performance_bonus(conn, username, password, year, month):
    """
    串接所有流程：抓取數據、計算獎金、發配給符合資格的員工。
    """
    report = {
        'target_count': 0,
        'bonus_per_person': 0,
        'eligible_employees_df': None,
        'saved_count': 0,
        'errors': []
    }

    try:
        # 1. 獲取月份的起迄日期
        start_date, end_date = get_monthly_dates(year, month)

        # 2. 呼叫爬蟲，獲取目標人數
        target_count = scraper.fetch_performance_count(username, password, start_date, end_date)
        report['target_count'] = target_count
        
        # 3. 計算每人應得獎金
        bonus_amount = target_count * 50
        report['bonus_per_person'] = bonus_amount

        # 4. 找出當月有出勤紀錄的員工 (不論是否缺席)
        attendance_df = q_att.get_attendance_by_month(conn, year, month)
        if attendance_df.empty:
            # 如果沒有任何人有出勤紀錄，就直接返回
            return report
        
        # 取得不重複的員工ID與姓名
        eligible_employees_df = attendance_df[['employee_id', 'hr_code', 'name_ch']].drop_duplicates()
        report['eligible_employees_df'] = eligible_employees_df.rename(columns={
            'hr_code': '員工編號', 'name_ch': '員工姓名'
        })
        
        # 5. 準備要存入資料庫的資料
        bonus_data_df = eligible_employees_df[['employee_id']].copy()
        bonus_data_df['bonus_amount'] = bonus_amount
        
        # 6. 呼叫資料庫函式，儲存獎金
        saved_count = q_perf.save_performance_bonuses(conn, year, month, bonus_data_df)
        report['saved_count'] = saved_count
        
    except Exception as e:
        report['errors'].append(str(e))
        
    return report