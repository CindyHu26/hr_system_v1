# page_crud_attendance.py
import streamlit as st
import pandas as pd
from datetime import datetime, time
import re
import traceback
from utils import (
    get_attendance_by_month,
    add_attendance_record,
    delete_attendance_record,
    get_all_employees,
    read_attendance_file,
    match_employee_id,
    insert_attendance
)

def show_page(conn):
    st.header("出勤紀錄管理與匯入")

    # 使用頁籤來區分功能
    tab1, tab2 = st.tabs(["查詢與手動管理 (CRUD)", "批次匯入打卡檔"])

    # --- 頁籤 1: 查詢與手動管理 (CRUD) ---
    with tab1:
        st.subheader("查詢特定月份紀錄")
        c1, c2 = st.columns(2)
        today = datetime.now()
        year = c1.number_input("選擇年份", min_value=2020, max_value=today.year + 5, value=today.year, key="att_year")
        month = c2.number_input("選擇月份", min_value=1, max_value=12, value=today.month, key="att_month")
        
        try:
            att_df = get_attendance_by_month(conn, year, month)
            st.dataframe(att_df, use_container_width=True)

            st.write("---")
            st.subheader("手動操作紀錄")
            
            # 使用 Expander 提供新增與刪除功能，介面更簡潔
            with st.expander("新增單筆出勤紀錄"):
                with st.form("add_attendance_form", clear_on_submit=True):
                    all_employees = get_all_employees(conn)
                    emp_options = {f"{name} ({code})": emp_id for name, code, emp_id in zip(all_employees['name_ch'], all_employees['hr_code'], all_employees['id'])}
                    
                    selected_emp_display = st.selectbox("選擇員工", options=emp_options.keys())
                    att_date = st.date_input("出勤日期", value=None)
                    c1_form, c2_form = st.columns(2)

                    # --- 2. [核心修正] 將預設值改為正確的 time 物件 ---
                    checkin_time_obj = c1_form.time_input("簽到時間", value=time(8, 0))
                    checkout_time_obj = c2_form.time_input("簽退時間", value=time(17, 0))
                    
                    submitted = st.form_submit_button("新增紀錄")
                    if submitted:
                        # 將 time 物件轉換為字串再存入資料庫
                        checkin_str = checkin_time_obj.strftime('%H:%M:%S') if checkin_time_obj else None
                        checkout_str = checkout_time_obj.strftime('%H:%M:%S') if checkout_time_obj else None

                        if selected_emp_display and att_date:
                            new_data = {
                                'employee_id': emp_options[selected_emp_display],
                                'date': att_date.strftime('%Y-%m-%d'),
                                'checkin_time': checkin_str,
                                'checkout_time': checkout_str
                            }
                            add_attendance_record(conn, new_data)
                            st.success("新增成功！")
                            st.rerun()
                        else:
                            st.error("員工和出勤日期為必填項！")
            
            with st.expander("刪除單筆出勤紀錄"):
                st.warning("請小心操作！刪除後無法復原。")
                if not att_df.empty:
                    # 讓使用者可以從當前顯示的紀錄中選擇
                    record_options = {f"ID: {row['紀錄ID']} - {row['姓名']} @ {row['日期']}": row['紀錄ID'] for index, row in att_df.iterrows()}
                    selected_record_display = st.selectbox("從上方列表選擇要刪除的紀錄", options=record_options.keys())
                    
                    if st.button("確認刪除選中紀錄", type="primary"):
                        record_id_to_delete = record_options[selected_record_display]
                        deleted_count = delete_attendance_record(conn, record_id_to_delete)
                        if deleted_count > 0:
                            st.success(f"已成功刪除紀錄 ID: {record_id_to_delete}")
                            st.rerun()
                        else:
                            st.error("刪除失敗，可能紀錄已被他人刪除。")
                else:
                    st.info("當前月份沒有可刪除的紀錄。")

        except Exception as e:
            st.error(f"讀取或操作出勤紀錄時發生錯誤: {e}")

    # --- 頁籤 2: 批次匯入打卡檔 ---
    with tab2:
        st.subheader("從打卡機檔案批次匯入")
        st.info("系統將使用「姓名」作為唯一匹配依據，並自動忽略姓名中的所有空格。請確保打卡檔姓名與員工資料庫中的姓名一致。")
        
        uploaded_file = st.file_uploader("上傳打卡機檔案 (XLS)", type=['xls'])
        
        if uploaded_file:
            df = read_attendance_file(uploaded_file)
            
            if df is not None and not df.empty:
                st.write("---")
                st.subheader("1. 檔案解析預覽")
                st.dataframe(df.head(5))

                st.write("---")
                st.subheader("2. 員工姓名匹配")
                try:
                    emp_df = get_all_employees(conn)
                    if emp_df.empty:
                        st.error("資料庫中沒有員工資料，無法進行匹配。請先至「員工管理」頁面新增員工。")
                        return
                    
                    df_matched = match_employee_id(df, emp_df)
                    
                    matched_count = df_matched['employee_id'].notnull().sum()
                    unmatched_count = len(df_matched) - matched_count
                    
                    st.info(f"匹配結果：成功 **{matched_count}** 筆 / 失敗 **{unmatched_count}** 筆。")

                    if unmatched_count > 0:
                        st.error(f"有 {unmatched_count} 筆紀錄匹配失敗，將不會被匯入：")
                        
                        unmatched_df = df_matched[df_matched['employee_id'].isnull()]
                        st.dataframe(unmatched_df[['hr_code', 'name_ch', 'date']])

                        with st.expander("🔍 點此展開進階偵錯，查看失敗原因"):
                            st.warning("此工具會顯示資料的「原始樣貌」，幫助您找出例如空格、特殊字元等看不見的差異。")
                            for index, row in unmatched_df.iterrows():
                                report_name = row['name_ch']
                                report_code = row['hr_code']
                                st.markdown(f"--- \n#### 正在分析失敗紀錄: **{report_name} ({report_code})**")
                                
                                st.markdown("**打卡檔中的原始資料：**")
                                st.code(f"姓名: {report_name!r}")

                                st.markdown("**資料庫中的潛在匹配：**")
                                # 修正 AttributeError: 'Series' object has no attribute 'lower' 的錯誤
                                # 並簡化邏輯，只比對淨化後的姓名
                                emp_df['match_key_name_debug'] = emp_df['name_ch'].astype(str).apply(lambda x: re.sub(r'\s+', '', x))
                                report_name_clean = re.sub(r'\s+', '', report_name)
                                
                                potential_match_name = emp_df[emp_df['match_key_name_debug'] == report_name_clean]
                                
                                if not potential_match_name.empty:
                                    st.write("依據「姓名」找到的相似資料：")
                                    for _, db_row in potential_match_name.iterrows():
                                        st.code(f"姓名: {db_row['name_ch']!r}, 資料庫編號: {db_row['hr_code']!r}")
                                else:
                                    st.info("在資料庫中找不到任何姓名相同的員工，請至「員工管理」頁面新增該員工。")

                    st.write("---")
                    st.subheader("3. 匯入資料庫")
                    if st.button("確認匯入資料庫", disabled=(matched_count == 0)):
                        with st.spinner("正在寫入資料庫..."):
                            inserted_count = insert_attendance(conn, df_matched)
                        st.success(f"處理完成！成功匯入/更新了 {inserted_count} 筆出勤紀錄！")
                        st.info("注意：匯入的僅為「成功匹配」的紀錄。")

                except Exception as e:
                    st.error(f"匹配或匯入過程中發生錯誤：{e}")
                    st.error(traceback.format_exc())
            else:
                st.error("檔案解析失敗，請確認檔案格式是否為正確的 report.xls 檔案。")