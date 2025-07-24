# services/leave_logic.py
"""
此模組包含請假紀錄相關的商業邏輯。
- 從 Google Sheet 或 Excel 檔案讀取假單。
- 精確計算請假時數（扣除午休、假日）。
"""
import pandas as pd
import requests
import io
from datetime import datetime, time, date, timedelta
import traceback
import streamlit as st
from bs4 import BeautifulSoup # 【關鍵修正 1】補上缺少的 import

# --- 核心功能函式 ---

@st.cache_data
def fetch_taiwan_calendar(year: int):
    """
    從政府資料開放平臺抓取指定年份的行事曆，並解析出假日與補班日。
    使用快取確保同一年份只抓取一次。
    """
    st.info(f"正在從網路同步 {year} 年的台灣政府行政機關行事曆...")
    try:
        dataset_url = "https://data.gov.tw/dataset/14718"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(dataset_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        link_element = soup.select_one("a.btn.btn-outline-secondary[href$='.csv']")
        
        if not link_element:
            st.error("在政府資料開放平臺上找不到 CSV 下載連結，網站結構可能已變更。")
            return set(), set()
            
        csv_url = link_element['href']
        
        response = requests.get(csv_url, headers=headers)
        response.raise_for_status()
        
        csv_content = response.content.decode('utf-8-sig')
        df = pd.read_csv(io.StringIO(csv_content))

        df['date'] = pd.to_datetime(df['date'], format='%Y%m%d').dt.date
        
        holidays = set(df[df['isHoliday'] == '2']['date'])
        workdays = set(df[df['isHoliday'] == '0']['date'])
        
        st.success(f"成功同步 {year} 年行事曆！")
        return holidays, workdays

    except Exception as e:
        st.error(f"抓取 {year} 年行事曆時發生錯誤: {e}")
        return set(), set()

def calculate_leave_hours(start_dt, end_dt):
    """
    接收 datetime 物件，精確計算請假時數。
    """
    if pd.isna(start_dt) or pd.isna(end_dt) or end_dt < start_dt:
        return 0.0

    is_full_day = start_dt.time() == time(0, 0)

    years_to_fetch = set(range(start_dt.year, end_dt.year + 1))
    all_holidays, all_makeup_workdays = set(), set()
    for year_to_fetch in years_to_fetch:
        h, w = fetch_taiwan_calendar(year_to_fetch)
        all_holidays.update(h)
        all_makeup_workdays.update(w)
        
    total_hours = 0.0
    work_start, lunch_start = time(8, 0), time(12, 0)
    lunch_end, work_end = time(13, 0), time(17, 0)
    
    current_date = start_dt.date()
    while current_date <= end_dt.date():
        is_weekend = current_date.weekday() >= 5
        is_holiday = current_date in all_holidays
        is_makeup_workday = current_date in all_makeup_workdays
        
        if (is_weekend and not is_makeup_workday) or (is_holiday and not is_makeup_workday):
            current_date += timedelta(days=1)
            continue

        day_leave_start = start_dt.time() if current_date == start_dt.date() else time.min
        day_leave_end = end_dt.time() if current_date == end_dt.date() else time.max
        
        if is_full_day:
            day_leave_start, day_leave_end = work_start, work_end
        
        am_overlap_start = max(day_leave_start, work_start)
        am_overlap_end = min(day_leave_end, lunch_start)
        if am_overlap_end > am_overlap_start:
            duration = datetime.combine(date.today(), am_overlap_end) - datetime.combine(date.today(), am_overlap_start)
            total_hours += duration.total_seconds() / 3600

        pm_overlap_start = max(day_leave_start, lunch_end)
        pm_overlap_end = min(day_leave_end, work_end)
        if pm_overlap_end > pm_overlap_start:
            duration = datetime.combine(date.today(), pm_overlap_end) - datetime.combine(date.today(), pm_overlap_start)
            total_hours += duration.total_seconds() / 3600
            
        current_date += timedelta(days=1)
        
    return round(total_hours, 2)

# 【關鍵修正 2】將所有邏輯整合到這個函式中，採用舊專案的穩健流程
def process_leave_file(source_input, year=None, month=None):
    """
    整合了讀取、篩選、計算的單一主函式。
    """
    try:
        # 步驟 1: 讀取並初步篩選出已通過的假單 (日期保持為字串)
        source_bytes = None
        if isinstance(source_input, str) and "docs.google.com/spreadsheets" in source_input:
            csv_export_url = source_input.replace('/edit?usp=sharing', '/export?format=csv')
            response = requests.get(csv_export_url)
            response.raise_for_status()
            source_bytes = response.content
        else:
            source_bytes = source_input.getvalue()

        content = source_bytes.decode('utf-8-sig')
        df = pd.read_csv(io.StringIO(content), dtype=str).fillna("")
        df.dropna(how='all', inplace=True)
        df = df[df['Status'].str.strip() == '已通過'].copy()
        
        if df.empty:
            raise ValueError("在整個資料來源中找不到任何「已通過」的假單。")

        # 步驟 2: 逐筆處理：進行月份篩選並計算時數
        processed_records = []
        for _, row in df.iterrows():
            try:
                # 在迴圈內逐筆轉換日期，保留時間
                start_date_obj = pd.to_datetime(row['Start Date'])
                end_date_obj = pd.to_datetime(row['End Date'])

                # 如果有指定月份，則進行篩選
                if year is not None and month is not None:
                    if not (start_date_obj.year == year and start_date_obj.month == month):
                        continue # 不符合月份，跳過此筆紀錄

                # 只有符合條件的假單才會觸發時數計算（和行事曆抓取）
                leave_hours = calculate_leave_hours(start_date_obj, end_date_obj)
                
                new_row = row.to_dict()
                new_row['Start Date'] = start_date_obj
                new_row['End Date'] = end_date_obj
                new_row["核算時數"] = leave_hours
                
                original_duration = pd.to_numeric(row.get('Duration (Hours)', row.get('Duration')), errors='coerce')
                if pd.notna(original_duration) and abs(original_duration - leave_hours) > 0.1:
                    new_row["備註"] = f"系統核算時數({leave_hours})與原單據時數({original_duration})不符"
                else:
                    new_row["備註"] = ""
                
                processed_records.append(new_row)

            except Exception as e:
                st.warning(f"跳過一筆無法處理的假單。Request ID: {row.get('Request ID', 'N/A')}, 錯誤: {e}")
                continue

        if not processed_records:
            if year and month:
                raise ValueError(f"在 {year} 年 {month} 月中，找不到任何有效的「已通過」假單紀錄。")
            else:
                raise ValueError("找不到任何有效的「已通過」假單紀錄。")


        # 步驟 3: 建立最終的 DataFrame
        result_df = pd.DataFrame(processed_records)
        
        cols_order = [
            'Employee Name', 'Type of Leave', 'Start Date', 'End Date',
            'Duration', 'Duration (Hours)', '核算時數', '備註', 'Request ID', 'Status'
        ]
        existing_cols = [col for col in cols_order if col in result_df.columns]
        other_cols = [col for col in result_df.columns if col not in existing_cols]
        
        return result_df[existing_cols + other_cols]

    except Exception as e:
        raise ValueError(f"處理請假檔案時發生錯誤: {e}")