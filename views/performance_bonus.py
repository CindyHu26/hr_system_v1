# views/performance_bonus.py
import streamlit as st
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
import traceback
from services import performance_bonus_logic as logic_perf

def show_page(conn):
    st.header("🏆 績效獎金計算")
    st.info("此功能將分步執行：抓取數據 → 確認人數 → 分配與微調 → 存檔。")

    if 'perf_bonus_step' not in st.session_state:
        st.session_state.perf_bonus_step = 1
    if 'perf_bonus_data' not in st.session_state:
        st.session_state.perf_bonus_data = {}

    if 'perf_bonus_message' in st.session_state:
        msg = st.session_state.perf_bonus_message
        if msg['type'] == 'warning':
            st.warning(msg['text'])
        del st.session_state.perf_bonus_message


    # ==================== 步驟 1: 輸入資訊並抓取人數 ====================
    if st.session_state.perf_bonus_step == 1:
        st.subheader("步驟 1: 輸入資訊並抓取目標人數")
        with st.form("perf_bonus_form_step1"):
            c1, c2 = st.columns(2)
            username = c1.text_input("聘軒系統帳號", type="password")
            password = c2.text_input("聘軒系統密碼", type="password")

            c3, c4 = st.columns(2)
            today = datetime.now()
            last_month = today - relativedelta(months=1)
            year = c3.number_input("獎金歸屬年份", 2020, today.year + 1, last_month.year)
            month = c4.number_input("獎金歸屬月份", 1, 12, last_month.month)
            
            submitted = st.form_submit_button("1. 抓取目標人數", type="primary")

        if submitted:
            if not username or not password:
                st.error("請輸入帳號與密碼！")
            else:
                with st.spinner("正在登入外部系統並抓取數據..."):
                    try:
                        target_count = logic_perf.fetch_target_count(username, password, year, month)
                        st.session_state.perf_bonus_data = {
                            'year': year, 'month': month,
                            'fetched_count': target_count, 'final_count': target_count
                        }
                        st.session_state.perf_bonus_step = 2
                        st.rerun()
                    except Exception as e:
                        st.error(f"抓取數據時發生錯誤：{e}")
                        st.code(traceback.format_exc())

    # ==================== 步驟 2: 確認人數並分配獎金 ====================
    elif st.session_state.perf_bonus_step == 2:
        data = st.session_state.perf_bonus_data
        st.subheader(f"步驟 2: 確認 {data['year']} 年 {data['month']} 月的獎金計算基準")

        st.success(f"✅ 系統成功抓取到目標人數為: **{data['fetched_count']}** 人")
        
        final_count = st.number_input(
            "請確認或手動修正最終用於計算的人數:", min_value=0, value=data['final_count']
        )
        st.session_state.perf_bonus_data['final_count'] = final_count
        
        bonus_per_person = final_count * 50
        st.info(f"🔢 根據您確認的人數，每人獎金將設定為: **{final_count} x 50 = {bonus_per_person} 元**")
        st.session_state.perf_bonus_data['bonus_per_person'] = bonus_per_person

        if st.button("2. 分配獎金給當月出勤員工", type="primary"):
            with st.spinner("正在查詢當月出勤員工並分配獎金..."):
                try:
                    eligible_df = logic_perf.get_eligible_employees(conn, data['year'], data['month'])
                    if eligible_df.empty:
                        st.session_state.perf_bonus_message = {
                            "type": "warning",
                            "text": f"注意：在 {data['year']} 年 {data['month']} 月中找不到任何出勤紀錄，無法分配獎金。請先至「出勤紀錄管理」頁面匯入該月份的打卡資料。"
                        }
                        st.session_state.perf_bonus_step = 1
                    else:
                        eligible_df['bonus_amount'] = bonus_per_person
                        st.session_state.perf_bonus_data['distribution_df'] = eligible_df
                        st.session_state.perf_bonus_step = 3
                    st.rerun()
                except Exception as e:
                    st.error(f"查詢員工時發生錯誤：{e}")

        if st.button("返回上一步重新抓取"):
            st.session_state.perf_bonus_step = 1
            st.session_state.perf_bonus_data = {}
            st.rerun()

    # ==================== 步驟 3: 微調並儲存最終結果 ====================
    elif st.session_state.perf_bonus_step == 3:
        data = st.session_state.perf_bonus_data
        st.subheader(f"步驟 3: 微調 {data['year']} 年 {data['month']} 月的獎金分配並存檔")
        st.info("您可以在下表中手動修改單一員工的獎金金額。修改完成後，請點擊最下方的按鈕儲存。")
        
        edited_df = st.data_editor(
            data['distribution_df'],
            column_config={
                "employee_id": None,
                "hr_code": st.column_config.TextColumn("員工編號", disabled=True),
                "name_ch": st.column_config.TextColumn("員工姓名", disabled=True),
                "bonus_amount": st.column_config.NumberColumn(
                    "績效獎金金額", min_value=0, format="%d 元"
                ),
            },
            use_container_width=True, hide_index=True
        )

        st.markdown("---")
        total_bonus = edited_df['bonus_amount'].sum()
        st.markdown(f"#### 總計發出獎金: <font color='red'>**{total_bonus:,}**</font> 元", unsafe_allow_html=True)

        c1, c2 = st.columns([1,1])
        if c1.button("💾 儲存最終獎金分配", type="primary", use_container_width=True):
            with st.spinner("正在將最終結果寫入資料庫..."):
                try:
                    saved_count = logic_perf.save_final_bonuses(conn, data['year'], data['month'], edited_df)
                    st.success(f"成功儲存了 {saved_count} 筆績效獎金紀錄！")
                    st.session_state.perf_bonus_step = 1
                    st.session_state.perf_bonus_data = {}
                    st.rerun()
                except Exception as e:
                    st.error(f"儲存時發生錯誤: {e}")

        if c2.button("返回上一步修改人數", use_container_width=True):
            st.session_state.perf_bonus_step = 2
            if 'distribution_df' in st.session_state.perf_bonus_data:
                del st.session_state.perf_bonus_data['distribution_df']
            st.rerun()