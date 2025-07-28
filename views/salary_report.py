# views/salary_report.py
import streamlit as st
from datetime import datetime
from dateutil.relativedelta import relativedelta
import traceback
import pandas as pd

from services import monthly_report_generator as logic_monthly_report
from services.monthly_report_generator import calculate_cash_denominations

def show_page(conn):
    st.header("💵 薪資月報與薪資單")
    st.info("請選擇要產生報表的月份。系統將會撈取該月份**已鎖定 (final)** 的薪資單資料，產生三種報表供您下載。")

    c1, c2 = st.columns(2)
    today = datetime.now()
    last_month = today - relativedelta(months=1)
    year = c1.number_input("選擇年份", min_value=2020, max_value=today.year + 5, value=last_month.year)
    month = c2.number_input("選擇月份", min_value=1, max_value=12, value=last_month.month)

    if st.button("🚀 產生月度報表", type="primary"):
        try:
            with st.spinner(f"正在產生 {year}年{month}月 的三種薪資報表..."):
                # ▼▼▼ 修改：呼叫新的函式 ▼▼▼
                reports = logic_monthly_report.generate_monthly_salary_reports(conn, year, month)
                st.session_state.monthly_reports = reports
                st.success("報表產生成功！")
        except ValueError as ve:
            st.warning(str(ve))
        except Exception as e:
            st.error(f"產生報表時發生未知錯誤：{e}")
            st.code(traceback.format_exc())

    if 'monthly_reports' in st.session_state:
        reports = st.session_state.monthly_reports
        st.write("---")
        st.subheader("報表下載")
        
        roc_year = year - 1911
        
        c1_dl, c2_dl, c3_dl = st.columns(3)

        with c1_dl:
            st.markdown("##### 1. 薪資計算總表 (基礎)")
            st.download_button(
                label="📥 下載 Excel",
                data=reports['basic_excel'],
                file_name=f"薪資計算_{roc_year}{month:02d}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_basic"
            )

        with c2_dl:
            st.markdown("##### 2. 薪資計算總表 (完整)")
            st.download_button(
                label="📥 下載 Excel",
                data=reports['full_excel'],
                file_name=f"薪資計算(加)_{roc_year}{month:02d}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="dl_full"
            )

        with c3_dl:
            st.markdown("##### 3. 員工薪資單 (可列印)")
            st.download_button(
                label="📥 下載 Word",
                data=reports['payslip_docx'],
                file_name=f"薪資單_{roc_year}{month:02d}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="dl_payslip"
            )
        
        # --- 現金兌換建議 ---
        cash_payout_list = reports.get("cash_payout_list", [])
        
        if cash_payout_list:
            st.write("---")
            st.subheader("🏦 現金發薪兌換建議")
            
            total_cash = sum(cash_payout_list)
            num_cash_employees = len(cash_payout_list)
            
            st.info(f"本月共有 **{num_cash_employees}** 位員工需要發放現金，總金額為 **{int(total_cash):,}** 元。")
            
            # 呼叫新的現金計算函式，傳入每個人的金額列表
            denominations = calculate_cash_denominations(cash_payout_list)
            
            df_cash = pd.DataFrame({
                "幣別": [f"{k} 元" for k in denominations.keys()],
                "建議兌換總數 (張/個)": list(denominations.values())
            })
            
            st.table(df_cash[df_cash["建議兌換總數 (張/個)"] > 0]) # 只顯示數量大於0的