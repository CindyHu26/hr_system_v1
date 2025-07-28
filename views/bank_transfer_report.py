# views/bank_transfer_report.py
import streamlit as st
from datetime import datetime
from dateutil.relativedelta import relativedelta
import traceback
from services import bank_file_generator as logic_bank

def show_page(conn):
    st.header("🏦 銀行薪轉檔產製")
    st.info("請選擇薪資月份，系統將會為每個加保單位，分別產製一個可直接複製貼上至銀行範本的 Excel (.xlsx) 資料檔。")

    c1, c2 = st.columns(2)
    today = datetime.now()
    last_month = today - relativedelta(months=1)
    year = c1.number_input("選擇年份", min_value=2020, max_value=today.year + 5, value=last_month.year, key="bank_year")
    month = c2.number_input("選擇月份", min_value=1, max_value=12, value=last_month.month, key="bank_month")

    if st.button("🚀 產生薪轉資料檔 (Excel)", type="primary"):
        if 'bank_xlsx_files' in st.session_state:
            del st.session_state['bank_xlsx_files']
        try:
            with st.spinner(f"正在依據 {year}年{month}月 的薪資資料產生 Excel 檔案..."):
                # 呼叫新的 XLSX 產生函式
                xlsx_files = logic_bank.generate_bank_transfer_xlsx_files(conn, year, month)
                st.session_state.bank_xlsx_files = xlsx_files
                
                if xlsx_files:
                    st.success("Excel 資料檔已產生！")
                else:
                    st.info("在選定的月份中，查無已鎖定且需要銀行匯款的薪資紀錄。")

        except Exception as e:
            st.error(f"產生檔案時發生未知錯誤：{e}")
            st.code(traceback.format_exc())
    
    if 'bank_xlsx_files' in st.session_state and st.session_state.bank_xlsx_files:
        bank_files = st.session_state.bank_xlsx_files
        st.write("---")
        st.subheader("檔案下載")
        roc_year = year - 1911
        for company_name, file_data in bank_files.items():
            st.download_button(
                label=f"📥 下載 {company_name} 的匯入資料 (.xlsx)",
                data=file_data,
                file_name=f"台中銀匯入資料_{company_name}_{roc_year}{month:02d}.xlsx",
                # 修改 MIME type 以對應 .xlsx 檔案
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_bank_xlsx_{company_name}"
            )