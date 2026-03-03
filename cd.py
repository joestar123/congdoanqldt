import streamlit as st
import pandas as pd
import os
from datetime import datetime

# Cấu hình file Excel
FILE_NAME = "diem_cong_doan.xlsx"

# Khởi tạo file Excel nếu chưa tồn tại
def init_excel():
    if not os.path.exists(FILE_NAME):
        with pd.ExcelWriter(FILE_NAME, engine='openpyxl') as writer:
            pd.DataFrame({"Tên Thành viên": ["Nguyễn Văn A", "Trần Thị B", "Lê Văn C"]}).to_excel(writer, sheet_name="Thành viên", index=False)
            pd.DataFrame(columns=["Tên sự kiện", "Ngày diễn ra", "Thời gian bắt đầu", "Địa điểm", "Số điểm"]).to_excel(writer, sheet_name="Sự kiện", index=False)
            pd.DataFrame(columns=["Tên sự kiện", "Thành viên", "Số điểm"]).to_excel(writer, sheet_name="Nhật ký", index=False)

init_excel()

# Hàm tải/lưu dữ liệu
def load_data(sheet):
    try:
        return pd.read_excel(FILE_NAME, sheet_name=sheet)
    except:
        return pd.DataFrame()

def save_data(df, sheet):
    with pd.ExcelWriter(FILE_NAME, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
        df.to_excel(writer, sheet_name=sheet, index=False)

# Cấu hình giao diện chính
st.set_page_config(page_title="Quản lý Điểm Công Đoàn", layout="wide")
st.title("🎯 Ứng dụng Chấm Điểm Công Đoàn")

# ================= XỬ LÝ ĐĂNG NHẬP ADMIN =================
if "is_admin" not in st.session_state:
    st.session_state.is_admin = False

with st.sidebar:
    st.header("🔐 Dành cho Admin")
    if not st.session_state.is_admin:
        admin_pass = st.text_input("Nhập mật khẩu để quản lý:", type="password")
        if st.button("Đăng nhập"):
            # Lưu ý: Bạn cần cấu hình admin_password trong .streamlit/secrets.toml
            try:
                if admin_pass == st.secrets["admin_password"]:
                    st.session_state.is_admin = True
                    st.success("Đăng nhập thành công!")
                    st.rerun()
                else:
                    st.error("Mật khẩu không đúng!")
            except Exception:
                st.error("Chưa cấu hình mật khẩu trong Secrets!")
    else:
        st.success("✅ Đang quyền Admin")
        if st.button("Đăng xuất"):
            st.session_state.is_admin = False
            st.rerun()

# Đọc dữ liệu từ Excel
df_thanhvien = load_data("Thành viên")
df_sukien = load_data("Sự kiện")
df_nhatky = load_data("Nhật ký")

if not df_sukien.empty:
    df_sukien['Ngày diễn ra'] = pd.to_datetime(df_sukien['Ngày diễn ra'])

tab1, tab2, tab3 = st.tabs(["🏆 Bảng Xếp Hạng", "📅 Quản lý Sự Kiện", "✅ Điểm Danh & Chi Tiết"])

# ================= TAB 1: BẢNG XẾP HẠNG =================
with tab1:
    st.header("Bảng Xếp Hạng Điểm Tích Lũy")
    
    if not df_nhatky.empty and not df_sukien.empty:
        # Gộp Nhật ký với Sự kiện để lấy Ngày diễn ra
        df_merged = pd.merge(
            df_nhatky, 
            df_sukien[["Tên sự kiện", "Ngày diễn ra"]], 
            on="Tên sự kiện", 
            how="left"
        )
        
        # Tạo các cột thời gian
        df_merged['Năm'] = df_merged['Ngày diễn ra'].dt.year
        df_merged['Tháng'] = df_merged['Ngày diễn ra'].dt.month
        df_merged['Quý'] = df_merged['Ngày diễn ra'].dt.quarter

        # Bộ lọc thời gian
        col_filter1, col_filter2 = st.columns([1, 2])
        with col_filter1:
            view_type = st.radio("Xem điểm theo:", ["Tất cả", "Theo Năm", "Theo Quý", "Theo Tháng"], horizontal=True)

        filtered_df = df_merged.copy()
        
        with col_filter2:
            if view_type == "Theo Năm":
                years = sorted(df_merged['Năm'].unique(), reverse=True)
                selected_year = st.selectbox("Chọn năm:", years)
                filtered_df = df_merged[df_merged['Năm'] == selected_year]
                
            elif view_type == "Theo Quý":
                years = sorted(df_merged['Năm'].unique(), reverse=True)
                c1, c2 = st.columns(2)
                y = c1.selectbox("Năm:", years, key="q_year")
                q = c2.selectbox("Quý:", [1, 2, 3, 4])
                filtered_df = df_merged[(df_merged['Năm'] == y) & (df_merged['Quý'] == q)]
                
            elif view_type == "Theo Tháng":
                years = sorted(df_merged['Năm'].unique(), reverse=True)
                c1, c2 = st.columns(2)
                y = c1.selectbox("Năm:", years, key="m_year")
                m = c2.selectbox("Tháng:", list(range(1, 13)), index=datetime.now().month - 1)
                filtered_df = df_merged[(df_merged['Năm'] == y) & (df_merged['Tháng'] == m)]

        # Tính toán tổng điểm sau khi lọc
        tong_diem = filtered_df.groupby("Thành viên")["Số điểm"].sum().reset_index()
        
        # Kết hợp với danh sách tất cả thành viên để hiện cả người 0 điểm
        bang_xep_hang = pd.merge(df_thanhvien, tong_diem, left_on="Tên Thành viên", right_on="Thành viên", how="left")
        bang_xep_hang["Số điểm"] = bang_xep_hang["Số điểm"].fillna(0)
        bang_xep_hang = bang_xep_hang[["Tên Thành viên", "Số điểm"]].sort_values(by="Số điểm", ascending=False).reset_index(drop=True)
        
        st.subheader(f"Kết quả: {view_type}")
        st.dataframe(bang_xep_hang, use_container_width=True)
    else:
        st.info("Chưa có dữ liệu sự kiện hoặc điểm danh để hiển thị bảng xếp hạng.")

# ================= TAB 2: QUẢN LÝ SỰ KIỆN =================
with tab2:
    st.header("Danh Sách Sự Kiện")
    if not df_sukien.empty:
        # Hiển thị ngày ở định dạng dễ đọc hơn
        df_display = df_sukien.copy()
        df_display['Ngày diễn ra'] = df_display['Ngày diễn ra'].dt.date
        st.dataframe(df_display, use_container_width=True)
    else:
        st.write("Chưa có sự kiện nào được tạo.")
        
    st.divider()
    
    if st.session_state.is_admin:
        st.subheader("➕ Tạo Sự Kiện Mới")
        with st.form("form_tao_su_kien", clear_on_submit=True):
            col1, col2 = st.columns(2)
            with col1:
                ten_sk = st.text_input("Tên sự kiện")
                dia_diem = st.text_input("Địa điểm")
            with col2:
                ngay_sk = st.date_input("Ngày diễn ra")
                thoi_gian_sk = st.time_input("Thời gian bắt đầu")
                diem_sk = st.number_input("Số điểm", min_value=1, value=5, step=1)
            
            submit_btn = st.form_submit_button("Lưu sự kiện")
            if submit_btn:
                if ten_sk.strip() == "":
                    st.error("Vui lòng nhập tên sự kiện!")
                elif not df_sukien.empty and ten_sk in df_sukien["Tên sự kiện"].values:
                    st.error("Tên sự kiện đã tồn tại! Vui lòng chọn tên khác.")
                else:
                    new_event = pd.DataFrame({
                        "Tên sự kiện": [ten_sk],
                        "Ngày diễn ra": [pd.to_datetime(ngay_sk)],
                        "Thời gian bắt đầu": [thoi_gian_sk.strftime("%H:%M")],
                        "Địa điểm": [dia_diem],
                        "Số điểm": [diem_sk]
                    })
                    df_sukien = pd.concat([df_sukien, new_event], ignore_index=True)
                    save_data(df_sukien, "Sự kiện")
                    st.success(f"Đã thêm sự kiện: {ten_sk}.")
                    st.rerun()

        st.divider()
        st.subheader("🗑️ Xóa Sự Kiện")
        if not df_sukien.empty:
            su_kien_can_xoa = st.selectbox("Chọn sự kiện cần xóa:", df_sukien["Tên sự kiện"].tolist())
            if st.button("Xóa sự kiện này", type="primary"):
                df_sukien = df_sukien[df_sukien["Tên sự kiện"] != su_kien_can_xoa]
                save_data(df_sukien, "Sự kiện")
                if not df_nhatky.empty:
                    df_nhatky = df_nhatky[df_nhatky["Tên sự kiện"] != su_kien_can_xoa]
                    save_data(df_nhatky, "Nhật ký")
                st.success(f"Đã xóa thành công sự kiện: {su_kien_can_xoa}")
                st.rerun()
    else:
        st.info("🔒 Vui lòng đăng nhập Admin để quản lý sự kiện.")

# ================= TAB 3: ĐIỂM DANH & CHI TIẾT SỰ KIỆN =================
with tab3:
    st.header("Điểm Danh Thành Viên Tham Gia")
    
    if not df_sukien.empty:
        danh_sach_su_kien = df_sukien["Tên sự kiện"].tolist()
        danh_sach_su_kien.reverse()
        
        selected_event = st.selectbox("📌 Chọn sự kiện để xem chi tiết hoặc điểm danh:", danh_sach_su_kien)
        
        if selected_event:
            event_info = df_sukien[df_sukien["Tên sự kiện"] == selected_event].iloc[0]
            diem_cua_su_kien = event_info["Số điểm"]
            ngay_ht = event_info['Ngày diễn ra'].date() if isinstance(event_info['Ngày diễn ra'], datetime) else event_info['Ngày diễn ra']
            
            st.markdown(f"**Thông tin:** Ngày **{ngay_ht}** | ⏰ **{event_info['Thời gian bắt đầu']}** | 📍 **{event_info['Địa điểm']}** | 🏆 **{diem_cua_su_kien} điểm**")
            
            da_tham_gia = []
            if not df_nhatky.empty:
                da_tham_gia = df_nhatky[df_nhatky["Tên sự kiện"] == selected_event]["Thành viên"].tolist()
            
            st.divider()
            
            if st.session_state.is_admin:
                danh_sach_tv = df_thanhvien["Tên Thành viên"].tolist()
                thanh_vien_chon = st.multiselect(
                    "✅ Chọn các thành viên tham gia:", 
                    options=danh_sach_tv,
                    default=da_tham_gia
                )
                
                if st.button("Lưu danh sách điểm danh"):
                    if not df_nhatky.empty:
                        df_nhatky = df_nhatky[df_nhatky["Tên sự kiện"] != selected_event]
                    
                    if thanh_vien_chon:
                        new_logs = pd.DataFrame({
                            "Tên sự kiện": [selected_event] * len(thanh_vien_chon),
                            "Thành viên": thanh_vien_chon,
                            "Số điểm": [diem_cua_su_kien] * len(thanh_vien_chon)
                        })
                        df_nhatky = pd.concat([df_nhatky, new_logs], ignore_index=True)
                        
                    save_data(df_nhatky, "Nhật ký")
                    st.success("🎉 Đã cập nhật điểm danh thành công!")
                    st.rerun()
            else:
                if da_tham_gia:
                    st.write("**👥 Danh sách thành viên đã tham gia:**")
                    cols = st.columns(3)
                    for i, tv in enumerate(da_tham_gia):
                        cols[i % 3].markdown(f"- {tv}")
                else:
                    st.write("Chưa có thành viên nào được điểm danh.")
    else:
        st.write("Chưa có sự kiện nào.")