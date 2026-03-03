import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import numpy as np

# ================= 1. CẤU HÌNH & KẾT NỐI (OPTIMIZED) =================
SHEET_NAME = "diem_cong_doan" 

@st.cache_resource # Cache client để không phải login lại nhiều lần
def get_gspread_client():
    creds_info = st.secrets["gcp_service_account"].to_dict()
    if "private_key" in creds_info:
        creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
    
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scope)
    return gspread.authorize(creds)

# Khởi tạo kết nối một lần duy nhất
client = get_gspread_client()
sh = client.open(SHEET_NAME)

# 🟢 QUAN TRỌNG: Cache dữ liệu trong 5 phút (300 giây) để tránh lỗi Quota
@st.cache_data(ttl=300) 
def load_data(sheet_name):
    try:
        worksheet = sh.worksheet(sheet_name)
        data = worksheet.get_all_records()
        df = pd.DataFrame(data)
        if "Ngày diễn ra" in df.columns:
            df["Ngày diễn ra"] = pd.to_datetime(df["Ngày diễn ra"], errors='coerce')
        return df
    except Exception:
        return pd.DataFrame()

def save_data(df, sheet_name):
    """Hàm lưu dữ liệu an toàn và làm mới Cache"""
    try:
        df_to_save = df.copy()
        
        # Đồng bộ định dạng ngày tháng sang chuỗi YYYY-MM-DD
        if "Ngày diễn ra" in df_to_save.columns:
            df_to_save["Ngày diễn ra"] = pd.to_datetime(df_to_save["Ngày diễn ra"]).dt.strftime('%Y-%m-%d')

        for col in df_to_save.select_dtypes(include=['datetime', 'datetimetz']).columns:
            df_to_save[col] = df_to_save[col].astype(str)

        df_to_save = df_to_save.replace([np.inf, -np.inf], np.nan).fillna("")

        def force_json_safe(val):
            if isinstance(val, (np.integer, np.int64)): return int(val)
            if isinstance(val, (np.floating, np.float64)): return float(val)
            if isinstance(val, (bool, np.bool_)): return bool(val)
            if pd.isna(val) or str(val) == "NaT": return ""
            return str(val)

        data_list = [df_to_save.columns.values.tolist()]
        for row in df_to_save.values.tolist():
            data_list.append([force_json_safe(v) for v in row])

        # Ghi dữ liệu
        worksheet = sh.worksheet(sheet_name)
        worksheet.clear() 
        worksheet.update(data_list)
        
        # 🟢 Xóa bộ nhớ đệm sau khi lưu để mọi người đều thấy dữ liệu mới nhất
        st.cache_data.clear()
        
    except Exception as e:
        st.error(f"❌ Lỗi khi lưu: {e}")

# ================= 2. GIAO DIỆN CHÍNH =================
st.set_page_config(page_title="Quản lý Công Đoàn", layout="wide")

# Nút làm mới dữ liệu thủ công (tiết kiệm API)
if st.sidebar.button("🔄 Tải lại dữ liệu"):
    st.cache_data.clear()
    st.rerun()

st.title("🎯 Ứng dụng Quản lý Điểm Công Đoàn")

# Quản lý Đăng nhập
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

with st.sidebar:
    st.header("🔐 Admin")
    if not st.session_state.is_admin:
        admin_pass = st.text_input("Mật khẩu:", type="password")
        if st.button("Đăng nhập"):
            if admin_pass == st.secrets["admin_password"]:
                st.session_state.is_admin = True
                st.rerun()
            else:
                st.error("Sai mật khẩu!")
    else:
        st.success("✅ Chế độ Admin")
        if st.button("Đăng xuất"):
            st.session_state.is_admin = False
            st.rerun()

# Load dữ liệu (Sử dụng Cache)
df_thanhvien = load_data("Thành viên")
df_sukien = load_data("Sự kiện")
df_nhatky = load_data("Nhật ký")

tab1, tab2, tab3 = st.tabs(["🏆 Bảng Xếp Hạng", "📅 Sự Kiện", "✅ Điểm Danh"])

# ================= TAB 1: BẢNG XẾP HẠNG =================
with tab1:
    if not df_nhatky.empty and not df_sukien.empty:
        df_merged = pd.merge(df_nhatky, df_sukien[["Tên sự kiện", "Ngày diễn ra"]], on="Tên sự kiện", how="left")
        df_merged['Ngày diễn ra'] = pd.to_datetime(df_merged['Ngày diễn ra'])
        df_merged = df_merged.dropna(subset=['Ngày diễn ra'])
        
        df_merged['Năm'] = df_merged['Ngày diễn ra'].dt.year.astype(int)
        df_merged['Tháng'] = df_merged['Ngày diễn ra'].dt.month.astype(int)
        
        view_type = st.radio("Lọc theo:", ["Tất cả", "Năm", "Tháng"], horizontal=True)
        filtered_df = df_merged.copy()
        
        if view_type != "Tất cả":
            years = sorted(df_merged['Năm'].unique(), reverse=True)
            y = st.selectbox("Năm:", years)
            filtered_df = df_merged[df_merged['Năm'] == y]
            if view_type == "Tháng":
                m = st.selectbox("Tháng:", list(range(1, 13)), index=datetime.now().month-1)
                filtered_df = filtered_df[filtered_df['Tháng'] == m]

        tong_diem = filtered_df.groupby("Thành viên")["Số điểm"].sum().reset_index()
        bxh = pd.merge(df_thanhvien, tong_diem, left_on="Tên Thành viên", right_on="Thành viên", how="left")
        bxh["Số điểm"] = bxh["Số điểm"].fillna(0)
        
        st.dataframe(bxh[["Tên Thành viên", "Số điểm"]].sort_values("Số điểm", ascending=False), use_container_width=True)
    else:
        st.info("Chưa có dữ liệu.")

# ================= TAB 2: QUẢN LÝ SỰ KIỆN =================
with tab2:
    if not df_sukien.empty:
        df_disp = df_sukien.copy()
        df_disp['Ngày diễn ra'] = df_disp['Ngày diễn ra'].dt.strftime('%Y-%m-%d')
        st.dataframe(df_disp, use_container_width=True)
    
    if st.session_state.is_admin:
        with st.expander("➕ Thêm sự kiện mới"):
            with st.form("add_sk"):
                c1, c2 = st.columns(2)
                ten = c1.text_input("Tên sự kiện")
                ngay = c2.date_input("Ngày")
                diem = c2.number_input("Điểm cộng", min_value=1, value=5)
                if st.form_submit_button("Lưu"):
                    new_sk = pd.DataFrame({"Tên sự kiện": [ten], "Ngày diễn ra": [pd.to_datetime(ngay)], "Số điểm": [diem]})
                    save_data(pd.concat([df_sukien, new_sk], ignore_index=True), "Sự kiện")
                    st.rerun()
        
        with st.expander("🗑️ Xóa sự kiện"):
            sk_xoa = st.selectbox("Chọn sự kiện:", df_sukien["Tên sự kiện"].tolist() if not df_sukien.empty else [])
            if st.button("Xác nhận xóa"):
                save_data(df_sukien[df_sukien["Tên sự kiện"] != sk_xoa], "Sự kiện")
                if not df_nhatky.empty:
                    save_data(df_nhatky[df_nhatky["Tên sự kiện"] != sk_xoa], "Nhật ký")
                st.rerun()

# ================= TAB 3: ĐIỂM DANH =================
with tab3:
    if not df_sukien.empty:
        sel_sk = st.selectbox("📌 Chọn sự kiện:", df_sukien["Tên sự kiện"].tolist()[::-1])
        info = df_sukien[df_sukien["Tên sự kiện"] == sel_sk].iloc[0]
        da_den = df_nhatky[df_nhatky["Tên sự kiện"] == sel_sk]["Thành viên"].tolist() if not df_nhatky.empty else []
        
        if st.session_state.is_admin:
            chon_tv = st.multiselect("✅ Thành viên tham gia:", df_thanhvien["Tên Thành viên"].tolist(), default=da_den)
            if st.button("Lưu điểm danh"):
                df_nk_other = df_nhatky[df_nhatky["Tên sự kiện"] != sel_sk] if not df_nhatky.empty else pd.DataFrame(columns=["Tên sự kiện", "Thành viên", "Số điểm"])
                new_logs = pd.DataFrame({"Tên sự kiện": [sel_sk]*len(chon_tv), "Thành viên": chon_tv, "Số điểm": [info["Số điểm"]]*len(chon_tv)})
                save_data(pd.concat([df_nk_other, new_logs], ignore_index=True), "Nhật ký")
                st.rerun()
        else:
            st.write(f"**Danh sách đã tham gia ({len(da_den)} người):**", ", ".join(da_den) if da_den else "Chưa có ai.")
