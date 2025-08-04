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
            st.subheader("批次修改出勤紀錄 (Excel)")
            st.info("此功能允許您下載特定員工的出勤紀錄範本，在 Excel 中修改後再上傳，系統會自動更新變更的紀錄。")

            # --- 模式選擇 ---
            edit_mode = st.radio(
                "選擇編輯模式",
                ("單人模式 (修改特定一位員工)", "多人模式 (修改多位員工)"),
                horizontal=True,
                key="att_edit_mode"
            )

            # --- 獲取員工列表 ---
            all_employees = q_emp.get_all_employees(conn)
            emp_options = {f"{name} ({code})": emp_id for name, code, emp_id in zip(all_employees['name_ch'], all_employees['hr_code'], all_employees['id'])}

            if edit_mode == "單人模式 (修改特定一位員工)":
                # 將 key 改為 "bulk_single_edit_selector" 以避免衝突
                selected_emp_key = st.selectbox(
                    "選擇要編輯的員工", 
                    options=emp_options.keys(), 
                    index=None, 
                    key="bulk_single_edit_selector" 
                )
                
                if selected_emp_key:
                    emp_id_list = [emp_options[selected_emp_key]]
                    file_name_prefix = f"attendance_{selected_emp_key}"
                    display_bulk_edit_interface(conn, emp_id_list, year, month, file_name_prefix)

            elif edit_mode == "多人模式 (修改多位員工)":
                from utils.ui_components import employee_selector # 局部導入
                
                st.markdown("##### 選擇要包含在範本中的員工")
                selected_emp_ids = employee_selector(conn, key_prefix="att_bulk_edit")
                
                if selected_emp_ids:
                    file_name_prefix = f"attendance_multiple_staff"
                    display_bulk_edit_interface(conn, selected_emp_ids, year, month, file_name_prefix)

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


def display_bulk_edit_interface(conn, emp_id_list, year, month, file_name_prefix):
    """一個共用的 UI 函式，用於顯示下載按鈕和上傳表單"""
    
    st.markdown("##### 步驟 1: 下載編輯範本")
    
    emp_att_df_list = []
    for emp_id in emp_id_list:
        df = q_att.get_attendance_by_employee_month(conn, emp_id, year, month)
        emp_info = q_common.get_by_id(conn, 'employee', emp_id)
        if df.empty:
             df = pd.DataFrame([{'id':None, 'employee_id': emp_id, 'date': f'{year}-{month}-01', 'checkin_time': None, 'checkout_time': None}])
        df['員工姓名'] = emp_info['name_ch'] if emp_info else '未知員工'
        emp_att_df_list.append(df)
    
    if not emp_att_df_list:
        st.warning("所選員工在此月份沒有任何出勤紀錄可供下載。")
        return

    full_emp_att_df = pd.concat(emp_att_df_list, ignore_index=True)
    
    output = io.BytesIO()
    df_for_export = full_emp_att_df[['id', '員工姓名', 'date', 'checkin_time', 'checkout_time']].copy()
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df_for_export.to_excel(writer, index=False, sheet_name='出勤紀錄')
    
    st.download_button(
        label=f"📥 下載 {month} 月出勤紀錄範本",
        data=output.getvalue(),
        file_name=f"{file_name_prefix}_{year}-{month:02d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    st.markdown("---")
    st.markdown("##### 步驟 2: 上傳修改後的檔案並儲存")
    with st.form(f"upload_edited_attendance_{file_name_prefix}"):
        uploaded_file = st.file_uploader("上傳修改後的 Excel 檔案", type=['xlsx'])
        
        if st.form_submit_button("💾 儲存變更", type="primary"):
            if uploaded_file:
                with st.spinner("正在讀取檔案並儲存變更..."):
                    try:
                        edited_df = pd.read_excel(uploaded_file, dtype={'checkin_time': str, 'checkout_time': str})
                        
                        # 讀取原始資料，用於比對和保留原始值
                        original_df = pd.concat([
                            q_att.get_attendance_by_employee_month(conn, emp_id, year, month) for emp_id in emp_id_list
                        ], ignore_index=True)

                        edited_df.dropna(subset=['id'], inplace=True)
                        edited_df['id'] = edited_df['id'].astype(int)

                        # 將編輯後的資料與原始資料合併，以便逐行比對
                        merged_df = pd.merge(original_df, edited_df, on='id', suffixes=('_orig', '_new'))

                        updates_count = 0
                        for _, row in merged_df.iterrows():
                            
                            # 預設使用原始資料庫中的時間
                            final_checkin_str = row.get('checkin_time_orig')
                            final_checkout_str = row.get('checkout_time_orig')

                            # 檢查 Excel 中的簽到時間是否為有效值
                            new_checkin_val = row.get('checkin_time_new')
                            if pd.notna(new_checkin_val) and str(new_checkin_val).strip() not in ['-', '']:
                                final_checkin_str = str(new_checkin_val)
                            
                            # 檢查 Excel 中的簽退時間是否為有效值
                            new_checkout_val = row.get('checkout_time_new')
                            if pd.notna(new_checkout_val) and str(new_checkout_val).strip() not in ['-', '']:
                                final_checkout_str = str(new_checkout_val)

                            # 只有在時間實際發生變更時才更新
                            if final_checkin_str != row.get('checkin_time_orig') or final_checkout_str != row.get('checkout_time_orig'):
                                
                                # 將最終確認的時間字串轉換為 time 物件
                                try:
                                    final_checkin_time = datetime.strptime(final_checkin_str, '%H:%M:%S').time() if final_checkin_str else time(0, 0)
                                except (TypeError, ValueError):
                                    final_checkin_time = time(0, 0)

                                try:
                                    final_checkout_time = datetime.strptime(final_checkout_str, '%H:%M:%S').time() if final_checkout_str else time(0, 0)
                                except (TypeError, ValueError):
                                    final_checkout_time = time(0, 0)

                                # 重新計算分鐘數並更新資料庫
                                new_minutes = logic_att.recalculate_attendance_minutes(final_checkin_time, final_checkout_time)
                                q_att.update_attendance_record(conn, row['id'], final_checkin_time, final_checkout_time, new_minutes)
                                updates_count += 1


                        if updates_count > 0:
                            st.success(f"成功更新了 {updates_count} 筆紀錄！")
                        else:
                            st.info("沒有偵測到任何有效的時間變更。")
                        st.rerun()

                    except Exception as e:
                        st.error(f"處理上傳檔案時發生錯誤：{e}")
            else:
                st.warning("請先上傳檔案。")