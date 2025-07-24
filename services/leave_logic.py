# services/leave_logic.py
"""
此模組包含請假紀錄相關的商業邏輯。
- 從 Google Sheet 或 Excel 檔案讀取假單。
- 精確計算請假時數（扣除午休、假日）。
"""
import pandas as pd
import requests
import io
import csv
from datetime import datetime, time, date, timedelta
import traceback
import streamlit as st
from bs4 import BeautifulSoup

# --- 核心功能函式 ---

@st.cache_data
def fetch_taiwan_calendar(year: int):
    """
    【二次修正版】根據您提供的最新HTML結構，能夠更精準地尋找下載連結，
    並排除掉非必要的檔案版本(如Google專用版)。
    【三次修正版】移除所有 st.info/success/error 提示，只回傳結果與狀態訊息。
    """
    try:
        roc_year = year - 1911
        dataset_url = "https://data.gov.tw/dataset/14718"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

        page_res = requests.get(dataset_url, headers=headers, timeout=15)
        page_res.raise_for_status()
        
        soup = BeautifulSoup(page_res.text, 'lxml')

        candidates = []
        for item in soup.select("li.resource-item"):
            link_element = item.select_one("a")
            if not link_element or not link_element.has_attr('href'):
                continue
            
            link_url = link_element['href']
            link_text = item.get_text(strip=True)

            if f"{roc_year}年" not in link_text: continue
            if 'csv' not in link_url.lower(): continue
            unwanted_keywords = ["Google", "iCal", "PDF", "ODS", "XML", "JSON"]
            if any(keyword.lower() in link_text.lower() for keyword in unwanted_keywords): continue

            candidates.append({"text": link_text, "url": link_url})
        
        if not candidates:
            return set(), set(), f"錯誤：在資料集頁面上找不到民國 {roc_year} 年的通用 CSV 檔案。"
        
        best_choice = candidates[0]
        for candidate in candidates:
            if "修正版" in candidate["text"]:
                best_choice = candidate
                break
        
        target_link = best_choice["url"]
        
        response = requests.get(target_link, headers=headers, timeout=15)
        response.raise_for_status()
        
        holidays = set()
        workdays = set()

        csv_file = io.StringIO(response.text)
        reader = csv.DictReader(csv_file)
        
        for row in reader:
            try:
                date_str = row.get("西元日期") or row.get("date")
                is_holiday_str = row.get("是否放假") or row.get("isHoliday")
                
                if not date_str or not is_holiday_str: continue

                d = datetime.strptime(date_str, "%Y%m%d").date()
                
                if is_holiday_str == '2': holidays.add(d)
                elif is_holiday_str == '0': workdays.add(d)
                
            except (ValueError, KeyError, TypeError): continue
        
        status_message = f"成功同步 {year} 年行事曆！(共 {len(holidays)} 個假日與 {len(workdays)} 個上班日)"
        return holidays, workdays, status_message
        
    except requests.RequestException as e:
        return set(), set(), f"抓取 {year} 年行事曆時發生網路錯誤: {e}"
    except Exception as e:
        return set(), set(), f"處理 {year} 年行事曆資料時發生未知錯誤: {e}"

def calculate_leave_hours(start_dt, end_dt, calendar_status_messages):
    """
    接收 datetime 物件，精確計算請假時數。
    """
    if pd.isna(start_dt) or pd.isna(end_dt) or end_dt < start_dt:
        return 0.0

    is_full_day = start_dt.time() == time(0, 0)

    years_to_fetch = set(range(start_dt.year, end_dt.year + 1))
    all_holidays, all_makeup_workdays = set(), set()
    for year_to_fetch in years_to_fetch:
        h, w, status_msg = fetch_taiwan_calendar(year_to_fetch)
        all_holidays.update(h)
        all_makeup_workdays.update(w)
        if status_msg not in calendar_status_messages:
            calendar_status_messages.append(status_msg)
        
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

        # 【關鍵修正】將所有 start_date 和 end_date 改為正確的參數名稱 start_dt 和 end_dt
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


def process_leave_file(source_input, year=None, month=None):
    """
    整合了讀取、篩選、計算的單一主函式。
    """
    calendar_sync_messages = []
    
    try:
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

        processed_records = []
        for _, row in df.iterrows():
            try:
                # 日期時間解析的邏輯維持不變，確保穩定性
                start_date_obj = pd.to_datetime(row['Start Date'])
                end_date_obj = pd.to_datetime(row['End Date'])

                if year is not None and month is not None:
                    if not (start_date_obj.year == year and start_date_obj.month == month):
                        continue

                leave_hours = calculate_leave_hours(start_date_obj, end_date_obj, calendar_sync_messages)
                
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
        
        if calendar_sync_messages:
            with st.expander("行事曆同步狀態", expanded=True):
                for msg in calendar_sync_messages:
                    if "成功" in msg:
                        st.write(f"✔️ {msg}")
                    else:
                        st.warning(f"⚠️ {msg}")

        if not processed_records:
            if year and month:
                raise ValueError(f"在 {year} 年 {month} 月中，找不到任何有效的「已通過」假單紀錄。")
            else:
                raise ValueError("找不到任何有效的「已通過」假單紀錄。")

        result_df = pd.DataFrame(processed_records)
        
        cols_order = [
            'Employee Name', 'Type of Leave', 'Start Date', 'End Date',
            'Duration', 'Duration (Hours)', '核算時數', '備註', 'Request ID', 'Status'
        ]
        existing_cols = [col for col in cols_order if col in result_df.columns]
        other_cols = [col for col in result_df.columns if col not in existing_cols]
        
        return result_df[existing_cols + other_cols]

    except Exception as e:
        if calendar_sync_messages:
            with st.expander("行事曆同步狀態", expanded=True):
                for msg in calendar_sync_messages:
                    if "成功" in msg:
                        st.write(f"✔️ {msg}")
                    else:
                        st.warning(f"⚠️ {msg}")
        raise ValueError(f"處理請假檔案時發生錯誤: {e}")