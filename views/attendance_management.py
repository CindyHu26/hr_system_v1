# views/attendance_management.py
import streamlit as st
import pandas as pd
from datetime import datetime, time
import traceback
from dateutil.relativedelta import relativedelta

# 導入新的、拆分後的查詢模組和服務模組
from db import queries_attendance as q_att
from db import queries_employee as q_emp # 用於通用 CRUD
from services import attendance_logic as logic_att

def show_page(conn):
    """
    顯示出勤紀錄管理頁面的主函式，包含手動管理與批次匯入功能。
    """
    st.header("📅 出勤紀錄管理")
    st.info("您可以在此查詢、手動新增單筆出勤紀錄，或從打卡機的 Excel 檔案批次匯入。")

    # 使用頁籤來區分功能
    tab1, tab2 = st.tabs(["查詢與手動管理", "從檔案批次匯入"])

    # --- 頁籤 1: 查詢與手動管理 ---
    with tab1:
        st.subheader("查詢與手動編輯紀錄")
        c1, c2 = st.columns(2)
        today = datetime.now()
        #  計算上一個月的年份和月份
        last_month = today - relativedelta(months=1)
        year = c1.number_input("選擇年份", min_value=2020, max_value=today.year + 5, value=last_month.year, key="att_year")
        month = c2.number_input("選擇月份", min_value=1, max_value=12, value=last_month.month, key="att_month")

        try:
            att_df = q_att.get_attendance_by_month(conn, year, month)
            st.dataframe(att_df.rename(columns={
                'id': '紀錄ID', 'hr_code': '員工編號', 'name_ch': '姓名', 'date': '日期',
                'checkin_time': '簽到時間', 'checkout_time': '簽退時間', 'late_minutes': '遲到(分)',
                'early_leave_minutes': '早退(分)', 'absent_minutes': '缺席(分)',
                'leave_minutes': '請假(分)',
                'overtime1_minutes': '加班1(分)', 'overtime2_minutes': '加班2(分)', 'overtime3_minutes': '加班3(分)',
                'note': '備註'
            }), use_container_width=True)

            with st.expander("手動新增/刪除紀錄"):
                # 新增紀錄
                st.markdown("##### 新增單筆紀錄")
                with st.form("add_attendance_form", clear_on_submit=True):
                    all_employees = q_emp.get_all_employees(conn)
                    emp_options = {f"{name} ({code})": emp_id for name, code, emp_id in zip(all_employees['name_ch'], all_employees['hr_code'], all_employees['id'])}
                    
                    selected_emp_display = st.selectbox("選擇員工", options=emp_options.keys())
                    att_date = st.date_input("出勤日期", value=None)
                    c1_form, c2_form = st.columns(2)
                    checkin_time_obj = c1_form.time_input("簽到時間", value=time(8, 30))
                    checkout_time_obj = c2_form.time_input("簽退時間", value=time(17, 30))
                    note_add = st.text_input("備註")

                    if st.form_submit_button("新增紀錄"):
                        if selected_emp_display and att_date:
                            new_data = {
                                'employee_id': emp_options[selected_emp_display],
                                'date': att_date.strftime('%Y-%m-%d'),
                                'checkin_time': checkin_time_obj.strftime('%H:%M:%S') if checkin_time_obj else None,
                                'checkout_time': checkout_time_obj.strftime('%H:%M:%S') if checkout_time_obj else None,
                                'note': note_add
                            }
                            # 使用通用的 add_record 函式
                            q_emp.add_record(conn, 'attendance', new_data)
                            st.success("新增成功！")
                            st.rerun()

                # 刪除紀錄
                st.markdown("---")
                st.markdown("##### 刪除單筆紀錄")
                if not att_df.empty:
                    record_options = {f"ID: {row['id']} - {row['name_ch']} @ {row['date']}": row['id'] for _, row in att_df.iterrows()}
                    selected_record_display = st.selectbox("從上方列表選擇要刪除的紀錄", options=record_options.keys(), index=None)
                    if st.button("確認刪除選中紀錄", type="primary"):
                        if selected_record_display:
                            record_id_to_delete = record_options[selected_record_display]
                            q_emp.delete_record(conn, 'attendance', record_id_to_delete)
                            st.success(f"已成功刪除紀錄 ID: {record_id_to_delete}")
                            st.rerun()
        except Exception as e:
            st.error(f"讀取或操作出勤紀錄時發生錯誤: {e}")

    # --- 頁籤 2: 批次匯入打卡檔 ---
    with tab2:
        st.subheader("從打卡機檔案批次匯入")
        st.info("系統將使用「姓名」作為唯一匹配依據，並自動忽略姓名中的所有空格。請確保打卡檔姓名與員工資料庫中的姓名一致。")
        
        uploaded_file = st.file_uploader("上傳打卡機檔案 (通常為 .xls 格式)", type=['xls', 'xlsx'])
        
        if uploaded_file:
            st.markdown("---")
            st.markdown("#### 步驟 1: 檔案解析與預覽")
            
            with st.spinner("正在解析您上傳的檔案..."):
                df, message = logic_att.read_attendance_file(uploaded_file)

            if df is None:
                st.error(f"檔案解析失敗：{message}")
            else:
                st.success(f"{message}，共讀取到 {len(df)} 筆原始紀錄。")
                st.dataframe(df.head())

                st.markdown("---")
                st.markdown("#### 步驟 2: 員工姓名匹配")
                with st.spinner("正在與資料庫員工進行姓名匹配..."):
                    try:
                        df_matched = logic_att.match_employees_by_name(conn, df)
                        matched_count = df_matched['employee_id'].notnull().sum()
                        unmatched_count = df_matched['employee_id'].isnull().sum()
                        
                        st.info(f"匹配結果：成功 **{matched_count}** 筆 / 失敗 **{unmatched_count}** 筆。")

                        if unmatched_count > 0:
                            st.error(f"以下 {unmatched_count} 筆紀錄因姓名無法匹配，將不會被匯入：")
                            st.dataframe(df_matched[df_matched['employee_id'].isnull()][['hr_code', 'name_ch', 'date']])
                        
                        st.markdown("---")
                        st.markdown("#### 步驟 3: 確認並匯入資料庫")
                        st.warning("匯入操作將會新增紀錄，如果員工在同一天的紀錄已存在，則會以檔案中的新資料覆蓋。")
                        
                        if st.button("確認匯入", type="primary", disabled=(matched_count == 0)):
                            with st.spinner("正在寫入資料庫..."):
                                affected_rows = q_att.batch_insert_or_update_attendance(conn, df_matched)
                            st.success(f"處理完成！共新增/更新了 {affected_rows} 筆出勤紀錄！")
                            st.info("您可以切換回「查詢與手動管理」頁籤查看最新結果。")
                    except Exception as e:
                        st.error(f"匹配或匯入過程中發生嚴重錯誤：{e}")
                        st.code(traceback.format_exc())