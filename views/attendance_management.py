# views/attendance_management.py
import streamlit as st
import pandas as pd
from datetime import datetime, time, timedelta
import traceback
import io
from dateutil.relativedelta import relativedelta

from db import queries_attendance as q_att
from db import queries_employee as q_emp
from db import queries_common as q_common
from services import attendance_logic as logic_att

def show_page(conn):
    st.header("📅 出勤紀錄管理")
    st.info("您可以在此查詢、批次匯入、或手動修改單筆出勤紀錄。")

    tab1, tab2 = st.tabs(["查詢與手動管理", "從檔案批次匯入"])

    with tab1:
        st.subheader("查詢與手動編輯紀錄")
        c1, c2 = st.columns(2)
        today = datetime.now()
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
            }), use_container_width=False, height=400)

            with st.expander("單筆修改簽到退 (適用於快速修正單日資料)"):
                if not att_df.empty:
                    record_options = {f"ID:{row['id']} - {row['name_ch']} @ {row['date']}": row['id'] for _, row in att_df.iterrows()}
                    selected_key = st.selectbox("從上方列表選擇要修改的紀錄", options=record_options.keys(), index=None, key="single_edit_selector")
                    if selected_key:
                        record_id = record_options[selected_key]
                        record_data = att_df[att_df['id'] == record_id].iloc[0]
                        with st.form(f"edit_attendance_{record_id}"):
                            st.write(f"正在修改 **{record_data['name_ch']}** 於 **{record_data['date']}** 的紀錄")
                            try: current_checkin = datetime.strptime(record_data['checkin_time'], '%H:%M:%S').time()
                            except (TypeError, ValueError): current_checkin = time(8, 0)
                            try: current_checkout = datetime.strptime(record_data['checkout_time'], '%H:%M:%S').time()
                            except (TypeError, ValueError): current_checkout = time(17, 0)
                            c1_edit, c2_edit = st.columns(2)
                            new_checkin = c1_edit.time_input("新的簽到時間", value=current_checkin, step=60)
                            new_checkout = c2_edit.time_input("新的簽退時間", value=current_checkout, step=60)
                            if st.form_submit_button("確認修改並重新計算時數", type="primary"):
                                with st.spinner("正在重新計算並儲存..."):
                                    new_minutes = logic_att.recalculate_attendance_minutes(new_checkin, new_checkout)
                                    q_att.update_attendance_record(conn, record_id, new_checkin, new_checkout, new_minutes)
                                    st.success(f"紀錄 ID:{record_id} 已更新！")
                                    st.rerun()
                else:
                    st.info("目前沒有可供修改的紀錄。")

            st.markdown("---")
            st.subheader("個人出勤記錄編輯區 (Excel 批次修改)")
            
            all_employees = q_emp.get_all_employees(conn)
            emp_options = {f"{name} ({code})": emp_id for name, code, emp_id in zip(all_employees['name_ch'], all_employees['hr_code'], all_employees['id'])}
            
            selected_emp_key = st.selectbox("選擇要編輯的員工", options=emp_options.keys(), index=None, key="bulk_edit_selector")

            if selected_emp_key:
                emp_id = emp_options[selected_emp_key]
                
                # 獲取該員工當月的出勤紀錄
                emp_att_df = q_att.get_attendance_by_employee_month(conn, emp_id, year, month)
                st.session_state.original_emp_att_df_for_excel = emp_att_df.copy() # 儲存原始資料供後續比對

                st.markdown("##### 步驟 1: 下載編輯範本")
                
                output = io.BytesIO()
                # 只提供最關鍵的欄位讓使用者修改
                df_for_export = emp_att_df[['id', 'date', 'checkin_time', 'checkout_time']].copy()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_for_export.to_excel(writer, index=False, sheet_name='出勤紀錄')
                
                st.download_button(
                    label=f"📥 下載 {selected_emp_key} 的 {month} 月出勤紀錄",
                    data=output.getvalue(),
                    file_name=f"attendance_{selected_emp_key}_{year}-{month:02d}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

                st.markdown("---")
                st.markdown("##### 步驟 2: 上傳修改後的檔案並儲存")
                with st.form("upload_edited_attendance"):
                    uploaded_file = st.file_uploader("上傳修改後的 Excel 檔案", type=['xlsx'])
                    
                    if st.form_submit_button("💾 儲存變更", type="primary"):
                        if uploaded_file:
                            with st.spinner("正在讀取檔案並儲存變更..."):
                                try:
                                    edited_df = pd.read_excel(uploaded_file, dtype={'checkin_time': str, 'checkout_time': str})
                                    original_df = st.session_state.original_emp_att_df_for_excel
                                    
                                    # 合併以找出差異
                                    merged_df = pd.merge(original_df, edited_df, on='id', suffixes=('_orig', '_new'))
                                    
                                    updates_count = 0
                                    for _, row in merged_df.iterrows():
                                        if row['checkin_time_orig'] != row['checkin_time_new'] or row['checkout_time_orig'] != row['checkout_time_new']:
                                            try: new_checkin = datetime.strptime(row['checkin_time_new'], '%H:%M:%S').time()
                                            except: new_checkin = time(0, 0)
                                            try: new_checkout = datetime.strptime(row['checkout_time_new'], '%H:%M:%S').time()
                                            except: new_checkout = time(0, 0)
                                                
                                            new_minutes = logic_att.recalculate_attendance_minutes(new_checkin, new_checkout)
                                            q_att.update_attendance_record(conn, row['id'], new_checkin, new_checkout, new_minutes)
                                            updates_count += 1
                                    
                                    st.success(f"成功更新了 {updates_count} 筆紀錄！")
                                    st.rerun()

                                except Exception as e:
                                    st.error(f"處理上傳檔案時發生錯誤：{e}")
                        else:
                            st.warning("請先上傳檔案。")

        except Exception as e:
            st.error(f"讀取或操作出勤紀錄時發生錯誤: {e}")
            st.code(traceback.format_exc())

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