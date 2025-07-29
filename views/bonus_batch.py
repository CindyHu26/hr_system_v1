# views/bonus_batch.py
import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import io
from openpyxl import Workbook
from openpyxl.utils.dataframe import dataframe_to_rows
from openpyxl.styles import Font, PatternFill


from services import bonus_scraper as scraper
from services import bonus_logic as logic_bonus
from db import queries_bonus as q_bonus
from db import queries_employee as q_emp

# --- 常數定義 ---
DEFAULT_COLS = ["序號", "雇主姓名", "入境日", "外勞姓名", "帳款名稱", "帳款日", "應收金額", "收款日", "實收金額", "業務員姓名", "source"]

# --- Excel 產生器 (維持不變) ---
def generate_bonus_excel(df: pd.DataFrame) -> io.BytesIO:
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        salespeople = df['業務員姓名'].unique()

        if len(salespeople) > 1:
            for person in salespeople:
                person_df = df[df['業務員姓名'] == person].copy()
                person_df.drop(columns=['業務員姓名'], inplace=True, errors='ignore')
                person_df.to_excel(writer, sheet_name=str(person), index=False)
        elif len(salespeople) == 1:
            person_df = df.copy()
            person_df.drop(columns=['業務員姓名'], inplace=True, errors='ignore')
            person_df.to_excel(writer, sheet_name=str(salespeople[0]), index=False)
        else:
            pd.DataFrame().to_excel(writer, sheet_name="無資料", index=False)

        for worksheet in writer.sheets.values():
            header_fill = PatternFill(start_color="DDEBF7", end_color="DDEBF7", fill_type="solid")
            bold_font = Font(bold=True)
            for cell in worksheet[1]:
                cell.fill = header_fill
                cell.font = bold_font
            for column_cells in worksheet.columns:
                length = max(len(str(cell.value)) for cell in column_cells)
                worksheet.column_dimensions[column_cells[0].column_letter].width = length + 2

    output.seek(0)
    return output


def show_page(conn):
    st.header("🌀 業務獎金管理")

    if 'bonus_details_df' not in st.session_state:
        st.session_state.bonus_details_df = pd.DataFrame(columns=DEFAULT_COLS)
    if 'bonus_summary_df' not in st.session_state:
        st.session_state.bonus_summary_df = pd.DataFrame()

    st.info("請先選擇要處理的獎金月份。")
    c1, c2, c3 = st.columns([2, 1, 1])
    today = datetime.now()
    last_month = today - relativedelta(months=1)
    year = c2.number_input("選擇年份", min_value=2020, max_value=today.year + 1, value=last_month.year, key="main_year")
    month = c3.number_input("選擇月份", min_value=1, max_value=12, value=last_month.month, key="main_month")

    tab1, tab2, tab3 = st.tabs(["📝 獎金明細維護 (草稿)", "📊 獎金總覽計算", "📖 歷史紀錄與匯出 (最終版)"])

    with tab1:
        st.subheader("步驟 1: 編輯獎金明細 (草稿)")

        if st.button(f"讀取 {year} 年 {month} 月的草稿"):
            with st.spinner("正在讀取草稿..."):
                draft_df = q_bonus.get_bonus_details_by_month(conn, year, month, status='draft')
                # --- 【核心修改】在讀取後立刻進行日期格式轉換 ---
                date_cols = ['入境日', '帳款日', '收款日']
                for col in date_cols:
                    if col in draft_df.columns:
                        draft_df[col] = pd.to_datetime(draft_df[col], errors='coerce').dt.date
                st.session_state.bonus_details_df = draft_df
                st.info(f"已載入 {len(draft_df)} 筆草稿紀錄。")

        employee_list = q_emp.get_all_employees(conn)['name_ch'].unique().tolist()

        st.write("您可以在下表中直接修改、刪除或新增獎金項目。完成所有編輯後，請點擊「💾 儲存草稿」。")
        edited_df = st.data_editor(
            st.session_state.bonus_details_df,
            num_rows="dynamic", use_container_width=True,
            column_config={
                "業務員姓名": st.column_config.SelectboxColumn("業務員姓名", options=employee_list, required=True),
                "帳款名稱": st.column_config.SelectboxColumn("帳款名稱", options=["服務費", "外仲"], required=True),
                "入境日": st.column_config.DateColumn("入境日", format="YYYY-MM-DD"),
                "帳款日": st.column_config.DateColumn("帳款日", format="YYYY-MM-DD"),
                "收款日": st.column_config.DateColumn("收款日", format="YYYY-MM-DD"),
                "應收金額": st.column_config.NumberColumn("應收金額", required=True),
                "實收金額": st.column_config.NumberColumn("實收金額", required=True),
                "source": st.column_config.TextColumn("來源", disabled=True),
            },
            key="bonus_details_editor"
        )
        st.session_state.bonus_details_df = edited_df

        btn_c1, btn_c2 = st.columns(2)
        with btn_c1:
            if st.button("💾 儲存草稿", use_container_width=True):
                df_to_save = st.session_state.bonus_details_df.dropna(
                    subset=['業務員姓名', '帳款名稱', '應收金額', '實收金額']
                )
                if len(df_to_save) < len(st.session_state.bonus_details_df):
                    st.error("儲存失敗！「業務員姓名、帳款名稱、應收金額、實收金額」為必填欄位，請檢查是否有空白的儲存格。")
                else:
                    with st.spinner("正在儲存您的變更..."):
                        df_to_save['source'].fillna('manual', inplace=True)
                        q_bonus.upsert_bonus_details_draft(conn, year, month, df_to_save)
                    st.success("草稿已成功儲存！")

        with btn_c2:
            with st.expander("從外部系統抓取資料"):
                with st.form("scrape_form"):
                    username = st.text_input("業績系統帳號", type="password")
                    password = st.text_input("業績系統密碼", type="password")
                    submitted = st.form_submit_button("執行資料抓取 (會覆蓋現有草稿)", type="primary")

                    if submitted:
                        progress_bar = st.progress(0, text="準備開始...")
                        with st.spinner("正在獲取員工名單..."):
                            employees_df = q_emp.get_all_employees(conn)
                            employee_names = employees_df['name_ch'].unique().tolist()
                        def progress_callback(message, percent):
                            progress_bar.progress(percent, text=message)
                        with st.spinner("正在遍歷所有業務員並抓取資料..."):
                            raw_details_df, not_found = scraper.fetch_all_bonus_data(username, password, year, month, employee_names, progress_callback)
                            raw_details_df['source'] = 'scraped'
                        
                        # --- 【核心修改】在抓取後也進行日期格式轉換 ---
                        date_cols = ['入境日', '帳款日', '收款日']
                        for col in date_cols:
                            if col in raw_details_df.columns:
                                raw_details_df[col] = pd.to_datetime(raw_details_df[col], errors='coerce').dt.date
                        
                        q_bonus.upsert_bonus_details_draft(conn, year, month, raw_details_df)
                        st.session_state.bonus_details_df = raw_details_df
                        st.success(f"資料抓取完成！共抓取 {len(raw_details_df)} 筆明細。")
                        if not_found:
                            st.warning(f"在系統中找不到員工: {', '.join(not_found)}")
                        st.rerun()

    with tab2:
        st.subheader("步驟 2: 計算獎金總覽")
        st.info(f"此處會根據您在「明細維護」頁籤中為 {year} 年 {month} 月儲存的最新草稿進行計算。")

        if st.button("🔄 根據最新草稿計算總覽", type="primary"):
            df_to_calc = q_bonus.get_bonus_details_by_month(conn, year, month, status='draft')
            if df_to_calc.empty:
                st.warning("目前沒有草稿資料可供計算。")
                st.session_state.bonus_summary_df = pd.DataFrame()
            else:
                with st.spinner("正在處理明細並計算獎金..."):
                    summary_df, _ = logic_bonus.process_and_calculate_bonuses(conn, df_to_calc, year, month)
                    st.session_state.bonus_summary_df = summary_df
                st.success("獎金總覽計算完成！")

        if not st.session_state.bonus_summary_df.empty:
            st.markdown("---")
            st.markdown("#### 計算結果預覽")
            st.dataframe(st.session_state.bonus_summary_df, use_container_width=True)

            st.markdown("---")
            st.subheader("步驟 3: 鎖定最終版本")
            st.warning(f"此操作將會把 {year} 年 {month} 月的獎金總額寫入薪資系統，並將所有相關明細標記為「最終版」，之後將無法再透過草稿功能修改。")

            if st.button("🔒 確認計算結果並鎖定", type="primary"):
                summary_df_to_save = st.session_state.bonus_summary_df
                if summary_df_to_save.empty:
                    st.error("沒有可鎖定的計算結果。")
                else:
                    try:
                        with st.spinner("正在寫入獎金總額並鎖定明細..."):
                            q_bonus.save_bonuses_to_monthly_table(conn, year, month, summary_df_to_save)
                            q_bonus.finalize_bonus_details(conn, year, month)
                        st.success(f"{year} 年 {month} 月的業務獎金已成功鎖定！")
                        st.session_state.bonus_details_df = pd.DataFrame(columns=DEFAULT_COLS)
                        st.session_state.bonus_summary_df = pd.DataFrame()
                        st.rerun()
                    except Exception as e:
                        st.error(f"鎖定時發生錯誤: {e}")
        else:
            st.info("點擊上方按鈕以計算獎金總覽。")

    with tab3:
        st.subheader("查詢最終版紀錄與匯出")
        st.info("您可以在此查詢已鎖定的最終版獎金明細，並匯出為 Excel 報表。")

        c1_hist, c2_hist = st.columns(2)
        hist_year = c1_hist.number_input("選擇年份", min_value=2020, max_value=today.year + 1, value=year, key="hist_year")
        hist_month = c2_hist.number_input("選擇月份", min_value=1, max_value=12, value=month, key="hist_month")

        if st.button("🔍 查詢最終版紀錄"):
            with st.spinner(f"正在查詢 {hist_year} 年 {hist_month} 月的最終版紀錄..."):
                final_df = q_bonus.get_bonus_details_by_month(conn, hist_year, hist_month, status='final')
                st.session_state.final_bonus_details_df = final_df

        if 'final_bonus_details_df' in st.session_state:
            final_df = st.session_state.final_bonus_details_df
            st.markdown("---")
            st.markdown("#### 查詢結果")
            st.dataframe(final_df, use_container_width=True)

            if not final_df.empty:
                excel_data = generate_bonus_excel(final_df)
                st.download_button(
                    label="📥 下載最終版明細 (Excel)",
                    data=excel_data,
                    file_name=f"業務獎金最終版_{hist_year}-{hist_month}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            else:
                st.warning("在選定的月份查無任何已鎖定的最終版紀錄。")