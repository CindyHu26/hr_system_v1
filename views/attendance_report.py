# views/attendance_report.py
import streamlit as st
from datetime import datetime
from dateutil.relativedelta import relativedelta
from services import report_generator as logic_report

def show_page(conn):
    st.header("📅 出勤日報表匯出")
    st.info("此功能會從資料庫撈取指定月份的所有出勤與請假紀錄，並產生格式化的 Excel 報表，所有員工將整合在單一工作表中，並以分頁符分隔。")

    st.subheader("選擇報表月份")
    c1, c2 = st.columns(2)
    today = datetime.now()
    last_month = today - relativedelta(months=1)
    
    year = c1.number_input("選擇年份", min_value=2020, max_value=today.year + 5, value=last_month.year, key="report_year")
    month = c2.number_input("選擇月份", min_value=1, max_value=12, value=last_month.month, key="report_month")

    if st.button("🚀 產生並下載 Excel 報表", type="primary"):
        with st.spinner(f"正在產生 {year} 年 {month} 月的出勤報表..."):
            try:
                # 呼叫報表產生器服務
                excel_data = logic_report.generate_attendance_excel(conn, year, month)
                
                # [核心修改] 計算民國年並更新檔名格式
                roc_year = year - 1911
                file_name = f"出勤日報表_民國{roc_year}年{month:02d}月.xlsx"

                st.download_button(
                    label="✅ 點此下載報表",
                    data=excel_data,
                    file_name=file_name,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            except ValueError as ve:
                st.warning(str(ve))
            except Exception as e:
                st.error(f"產生報表時發生錯誤: {e}")