# run.py (v2 - 修正版)
import streamlit.web.cli as stcli
import sys
import os

def get_streamlit_file_path(file_name):
    """
    獲取資源的正確路徑，無論是在開發環境還是打包後的環境。
    """
    if getattr(sys, 'frozen', False):
        # 如果是打包後的 .exe，檔案會被解壓縮到一個暫存資料夾
        # sys._MEIPASS 會指向那個暫存資料夾
        application_path = sys._MEIPASS
    else:
        # 如果是在開發環境，直接使用目前檔案的目錄
        application_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(application_path, file_name)

if __name__ == "__main__":
    # 獲取主程式 app.py 的路徑
    app_path = get_streamlit_file_path('app.py')
    
    # 設定 Streamlit 命令列參數
    sys.argv = [
        "streamlit",
        "run",
        app_path, # 使用我們動態找到的路徑
        "--global.developmentMode=false",
        "--server.headless=true",
        "--server.port", "8501"
    ]

    # 執行 Streamlit
    sys.exit(stcli.main())