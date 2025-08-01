# views/config_management.py
import streamlit as st
import pandas as pd
from datetime import datetime
from db import queries_config as q_config

# 預設值，當資料庫中找不到設定時使用
DEFAULT_CONFIGS = {
    'HOURLY_RATE_DIVISOR': {'value': '240.0', 'desc': '時薪計算基準 (月薪 / X)', 'type': 'number'},
    'NHI_SUPPLEMENT_RATE': {'value': '0.0211', 'desc': '二代健保補充保費費率', 'type': 'number'},
    'NHI_BONUS_MULTIPLIER': {'value': '4', 'desc': '個人高額獎金免扣額 (投保薪資倍數)', 'type': 'number'},
    'FOREIGNER_TAX_RATE_THRESHOLD_MULTIPLIER': {'value': '1.5', 'desc': '外籍稅務級距門檻 (基本工資倍數)', 'type': 'number'},
    'FOREIGNER_LOW_INCOME_TAX_RATE': {'value': '0.06', 'desc': '外籍稅務 - 較低稅率', 'type': 'number'},
    'FOREIGNER_HIGH_INCOME_TAX_RATE': {'value': '0.18', 'desc': '外籍稅務 - 較高稅率', 'type': 'number'},
    'NHI_BONUS_ITEMS': {'value': "津貼,津貼加班,特休未休,主管津貼,仲介師,加薪,補助,業務獎金,績效獎金", 'desc': '二代健保累計獎金項目 (用逗號分隔)', 'type': 'text_area'},
    'HEALTH_INSURANCE_URL': {'value': "https://www.nhi.gov.tw/ch/cp-17545-f87bd-2576-1.html", 'desc': '健保署保費負擔金額表網址', 'type': 'text'},
    'DEFAULT_GSHEET_URL': {'value': "請在此貼上您的Google Sheet分享連結", 'desc': '預設請假單來源 (Google Sheet)', 'type': 'text'},
}

def show_page(conn):
    st.header("🔧 系統參數設定")
    
    tab1, tab2 = st.tabs(["基本工資設定", "通用系統參數"])

    with tab1:
        st.subheader("歷年基本工資管理")
        st.info("薪資系統中的所有計算（如外籍稅務門檻）都將以此處設定的年度基本工資為基準。")
        try:
            wages_df = q_config.get_all_minimum_wages(conn)
            st.dataframe(wages_df, use_container_width=True)
        except Exception as e:
            st.error(f"讀取基本工資歷史時發生錯誤: {e}")
        
        with st.expander("新增或修改年度基本工資"):
            with st.form("upsert_wage_form"):
                current_year = datetime.now().year
                c1, c2 = st.columns(2)
                year = c1.number_input("年份*", min_value=2020, max_value=current_year + 5, value=current_year)
                wage = c2.number_input("基本工資金額*", min_value=0, step=100)
                c3, c4 = st.columns(2)
                effective_date = c3.date_input("生效日*", value=datetime(year, 1, 1))
                note = c4.text_input("備註", placeholder="例如：勞動部公告調整")

                if st.form_submit_button("儲存基本工資", type="primary"):
                    q_config.add_or_update_minimum_wage(conn, year, wage, effective_date, note)
                    st.success(f"已成功儲存 {year} 年的基本工資為 {wage} 元。")
                    st.rerun()

    with tab2:
        st.subheader("通用薪資與系統參數")
        st.info("此處的設定會影響所有薪資計算的細節與部分頁面的預設值。請謹慎修改。")

        configs_from_db = q_config.get_all_configs(conn)
        
        with st.form("update_general_config"):
            for key, details in DEFAULT_CONFIGS.items():
                db_value = configs_from_db.get(key)
                current_value = db_value if db_value is not None else details['value']
                
                if details['type'] == 'text_area':
                    st.text_area(f"{details['desc']}", value=current_value, key=f"config_{key}")
                elif details['type'] == 'text':
                    st.text_input(f"{details['desc']}", value=current_value, key=f"config_{key}")
                else: # number
                    st.number_input(f"{details['desc']}", value=float(current_value), key=f"config_{key}", format="%.4f")

            if st.form_submit_button("儲存通用參數", type="primary"):
                all_keys = list(DEFAULT_CONFIGS.keys())
                data_to_save = []
                for key in all_keys:
                    new_value = st.session_state[f"config_{key}"]
                    data_to_save.append((key, str(new_value)))
                
                q_config.batch_update_configs(conn, data_to_save)
                st.success("通用參數已成功儲存！")
                st.rerun()