import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import numpy as np

# ================= 1. CẤU HÌNH KẾT NỐI =================
# Tên chính xác của file Google Sheet của bạn
SHEET_NAME = "diem_cong_doan" 

def get_gspread_client():
    # .to_dict() giúp tạo ra một bản sao có thể chỉnh sửa được
    creds_info = st.secrets["gcp_service_account"].to_dict()
    
    # Bây giờ bạn có thể sửa private_key thoải mái
    if "private_key" in creds_info:
        creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n")
    
    scope = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    creds = Credentials.from_service_account_info(creds_info, scopes=scope)
    return gspread.authorize(creds)

# Khởi tạo kết nối
try:
    client = get_gspread_client()
    sh = client.open(SHEET_NAME)
except Exception as e:
    st.error(f"Không thể kết nối Google Sheets: {e}")
    st.stop()

def load_data(sheet_name):
    try:
        worksheet = sh.worksheet(sheet_name)
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()

def save_data(df, sheet_name):
    """Phiên bản an toàn: Chuẩn bị dữ liệu xong mới xóa/ghi đè"""
    try:
        # BƯỚC 1: CHUẨN BỊ DỮ LIỆU TRÊN BỘ NHỚ
        df_to_save = df.copy()
        
        # Chuyển đổi các cột ngày tháng sang chuỗi
        for col in df_to_save.select_dtypes(include=['datetime', 'datetimetz', 'timedelta']).columns:
            df_to_save[col] = df_to_save[col].astype(str)

        # Xử lý giá trị trống và vô cực
        df_to_save = df_to_save.replace([np.inf, -np.inf], np.nan).fillna("")

        # Ép kiểu dữ liệu về dạng Python thuần (để JSON đọc được)
        def force_json_safe(val):
            if isinstance(val, (np.integer, np.int64)): return int(val)
            if isinstance(val, (np.floating, np.float64)): return float(val)
            if isinstance(val, (bool, np.bool_)): return bool(val)
            if isinstance(val, (str, int, float)): return val
            return str(val)

        # Tạo danh sách dữ liệu (Header + Data)
        data_list = [df_to_save.columns.values.tolist()]
        for row in df_to_save.values.tolist():
            data_list.append([force_json_safe(v) for v in row])

        # BƯỚC 2: GHI VÀO GOOGLE SHEETS
        # Chỉ khi data_list đã tạo xong không lỗi, lệnh Clear mới chạy
        worksheet = sh.worksheet(sheet_name)
        worksheet.clear() 
        worksheet.update(data_list)
        
    except Exception as e:
        st.error(f"❌ Lỗi khi lưu dữ liệu vào '{sheet_name}': {e}")
        st.warning("⚠️ Dữ liệu cũ trên Sheets vẫn được giữ nguyên.")

# ================= 2. GIAO DIỆN & ADMIN =================
st.set_page_config(page_title="Quản lý Công Đoàn", layout="wide")
st.title("🎯 Ứng dụng Chấm Điểm Công Đoàn")

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
        st.success("✅ Admin Mode")
        if st.button("Đăng xuất"):
            st.session_state.is_admin = False
            st.rerun()

# Đọc dữ liệu từ Sheets
df_thanhvien = load_data("Thành viên")
df_sukien = load_data("Sự kiện")
df_nhatky = load_data("Nhật ký")

# Xử lý định dạng ngày tháng sau khi load
if not df_sukien.empty:
    df_sukien['Ngày diễn ra'] = pd.to_datetime(df_sukien['Ngày diễn ra'], errors='coerce')

tab1, tab2, tab3 = st.tabs(["🏆 Bảng Xếp Hạng", "📅 Quản lý Sự Kiện", "✅ Điểm Danh"])

# ================= TAB 1: BẢNG XẾP HẠNG =================
with tab1:
    st.header("Bảng Xếp Hạng Điểm Tích Lũy")
    if not df_nhatky.empty and not df_sukien.empty:
        df_merged = pd.merge(df_nhatky, df_sukien[["Tên sự kiện", "Ngày diễn ra"]], on="Tên sự kiện", how="left")
        # Đảm bảo cột ngày tháng hợp lệ
        df_merged['Ngày diễn ra'] = pd.to_datetime(df_merged['Ngày diễn ra'])
        df_merged['Năm'] = df_merged['Ngày diễn ra'].dt.year
        df_merged['Tháng'] = df_merged['Ngày diễn ra'].dt.month
        df_merged['Quý'] = df_merged['Ngày diễn ra'].dt.quarter

        c_f1, c_f2 = st.columns([1, 2])
        view_type = c_f1.radio("Xem theo:", ["Tất cả", "Theo Năm", "Theo Quý", "Theo Tháng"], horizontal=True)

        filtered_df = df_merged.copy()
        with c_f2:
            if view_type == "Theo Năm":
                years = sorted(df_merged['Năm'].dropna().unique().astype(int), reverse=True)
                y = st.selectbox("Chọn năm:", years)
                filtered_df = df_merged[df_merged['Năm'] == y]
            elif view_type == "Theo Quý":
                years = sorted(df_merged['Năm'].dropna().unique().astype(int), reverse=True)
                y = st.selectbox("Năm:", years, key="q_y")
                q = st.selectbox("Quý:", [1, 2, 3, 4])
                filtered_df = df_merged[(df_merged['Năm'] == y) & (df_merged['Quý'] == q)]
            elif view_type == "Theo Tháng":
                years = sorted(df_merged['Năm'].dropna().unique().astype(int), reverse=True)
                y = st.selectbox("Năm:", years, key="m_y")
                m = st.selectbox("Tháng:", list(range(1, 13)), index=datetime.now().month - 1)
                filtered_df = df_merged[(df_merged['Năm'] == y) & (df_merged['Tháng'] == m)]

        tong_diem = filtered_df.groupby("Thành viên")["Số điểm"].sum().reset_index()
        bxh = pd.merge(df_thanhvien, tong_diem, left_on="Tên Thành viên", right_on="Thành viên", how="left")
        bxh["Số điểm"] = bxh["Số điểm"].fillna(0)
        st.dataframe(bxh[["Tên Thành viên", "Số điểm"]].sort_values("Số điểm", ascending=False), use_container_width=True)
    else:
        st.info("Chưa có dữ liệu tính điểm.")

# ================= TAB 2: QUẢN LÝ SỰ KIỆN =================
with tab2:
    st.header("Danh Sách Sự Kiện")
    if not df_sukien.empty:
        df_disp = df_sukien.copy()
        df_disp['Ngày diễn ra'] = df_disp['Ngày diễn ra'].dt.date
        st.dataframe(df_disp, use_container_width=True)
    
    if st.session_state.is_admin:
        st.divider()
        st.subheader("➕ Thêm Sự Kiện")
        with st.form("add_sk", clear_on_submit=True):
            c1, c2 = st.columns(2)
            ten = c1.text_input("Tên sự kiện")
            diadiem = c1.text_input("Địa điểm")
            ngay = c2.date_input("Ngày")
            gio = c2.time_input("Giờ")
            diem = c2.number_input("Điểm", min_value=1, value=5)
            if st.form_submit_button("Lưu sự kiện"):
                if ten:
                    new_sk = pd.DataFrame({
                        "Tên sự kiện": [ten], 
                        "Ngày diễn ra": [ngay.strftime("%Y-%m-%d")], 
                        "Thời gian bắt đầu": [gio.strftime("%H:%M")], 
                        "Địa điểm": [diadiem], 
                        "Số điểm": [diem]
                    })
                    # Hợp nhất và lưu
                    df_sukien_updated = pd.concat([df_sukien, new_sk], ignore_index=True)
                    save_data(df_sukien_updated, "Sự kiện")
                    st.success("Đã thêm sự kiện!")
                    st.rerun()
                else:
                    st.error("Vui lòng nhập tên sự kiện!")

        st.divider()
        st.subheader("🗑️ Xóa Sự Kiện")
        if not df_sukien.empty:
            danh_sach_sk = df_sukien["Tên sự kiện"].tolist()
            sk_xoa = st.selectbox("Chọn sự kiện để xóa:", danh_sach_sk)
            if st.button("Xác nhận xóa sự kiện", type="primary"):
                # Xóa khỏi bảng Sự kiện
                df_sukien = df_sukien[df_sukien["Tên sự kiện"] != sk_xoa]
                save_data(df_sukien, "Sự kiện")
                
                # Xóa các dòng nhật ký liên quan để sạch dữ liệu điểm
                if not df_nhatky.empty:
                    df_nhatky = df_nhatky[df_nhatky["Tên sự kiện"] != sk_xoa]
                    save_data(df_nhatky, "Nhật ký")
                
                st.success(f"Đã xóa hoàn toàn sự kiện: {sk_xoa}")
                st.rerun()

# ================= TAB 3: ĐIỂM DANH =================
with tab3:
    if not df_sukien.empty:
        # Đảo ngược danh sách để sự kiện mới nhất lên đầu
        sk_list = df_sukien["Tên sự kiện"].tolist()[::-1]
        sel_sk = st.selectbox("📌 Chọn sự kiện điểm danh:", sk_list)
        
        # Lấy thông tin điểm của sự kiện đang chọn
        event_info = df_sukien[df_sukien["Tên sự kiện"] == sel_sk].iloc[0]
        
        # Lấy danh sách những người đã điểm danh trước đó
        da_den = []
        if not df_nhatky.empty:
            da_den = df_nhatky[df_nhatky["Tên sự kiện"] == sel_sk]["Thành viên"].tolist()
        
        if st.session_state.is_admin:
            chon_tv = st.multiselect(
                "✅ Chọn thành viên tham gia:", 
                df_thanhvien["Tên Thành viên"].tolist(), 
                default=da_den
            )
            
            if st.button("Cập nhật điểm danh"):
                # 1. Giữ lại nhật ký của các sự kiện KHÁC
                if not df_nhatky.empty:
                    df_nk_keep = df_nhatky[df_nhatky["Tên sự kiện"] != sel_sk]
                else:
                    df_nk_keep = pd.DataFrame(columns=["Tên sự kiện", "Thành viên", "Số điểm"])
                
                # 2. Tạo nhật ký MỚI cho sự kiện này
                if chon_tv:
                    new_logs = pd.DataFrame({
                        "Tên sự kiện": [sel_sk] * len(chon_tv), 
                        "Thành viên": chon_tv, 
                        "Số điểm": [event_info["Số điểm"]] * len(chon_tv)
                    })
                    df_nhatky_final = pd.concat([df_nk_keep, new_logs], ignore_index=True)
                else:
                    df_nhatky_final = df_nk_keep
                
                # 3. Lưu lại
                save_data(df_nhatky_final, "Nhật ký")
                st.success(f"Đã cập nhật điểm danh cho {len(chon_tv)} thành viên!")
                st.rerun()
        else:
            st.write("**Danh sách đã tham gia:**")
            if da_den:
                for i, name in enumerate(da_den, 1):
                    st.write(f"{i}. {name}")
            else:
                st.info("Chưa có thành viên nào được điểm danh.")
    else:
        st.warning("Vui lòng tạo sự kiện trước tại Tab 'Quản lý Sự Kiện'.")
