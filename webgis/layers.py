from pathlib import Path
import unicodedata

ROOT = Path(__file__).resolve().parent
INPUT = ROOT.parent / "LopWebGis"
REFERENCE = ROOT.parent / "mau" / "data.zip"
RUNTIME = ROOT / "var"
MIN_ZOOM = 7
MAX_ZOOM = 17

# Values from BaoCao.qgz for the three 2030 layers and the embedded QGIS styles
# of both baseline layers. The source file hashes and project links are in README.
RICE_FILL = "#e6ff00"
CONVERSION_COLORS = {
    "HNK": "#fff0b4",
    "CLN": "#ffd2a0",
    "NTS": "#aaffff",
    "CNT": "#e6e682",
    "NKH": "#f5ffb4",
}
CONVERSION_PURPOSES = {
    "HNK": "Đất trồng cây hằng năm khác",
    "CLN": "Đất trồng cây lâu năm",
    "NTS": "Đất nuôi trồng thủy sản",
    "CNT": "Đất chăn nuôi tập trung",
    "NKH": "Đất nông nghiệp khác",
}
NON_AGRICULTURAL_PURPOSES = {
    "ONT": "Đất ở tại nông thôn",
    "ODT": "Đất ở tại đô thị",
    "DGT": "Đất công trình giao thông",
    "TMD": "Đất thương mại, dịch vụ",
    "DKV": "Đất khu vui chơi, giải trí công cộng, sinh hoạt cộng đồng",
    "SKK": "Đất khu công nghiệp",
    "SKC": "Đất cơ sở sản xuất phi nông nghiệp",
    "DNL": "Đất công trình năng lượng, chiếu sáng công cộng",
    "SKN": "Đất cụm công nghiệp",
    "TSC": "Đất xây dựng trụ sở cơ quan",
    "DTL": "Đất công trình thủy lợi",
    "DSN": "Đất xây dựng công trình sự nghiệp",
    "DGD": "Đất xây dựng cơ sở giáo dục và đào tạo",
    "DTT": "Đất xây dựng cơ sở thể dục, thể thao",
    "SKS": "Đất sử dụng cho hoạt động khoáng sản",
    "NTD": "Đất nghĩa trang, nhà tang lễ, cơ sở hỏa táng, cơ sở lưu giữ tro cốt",
    "CQP": "Đất quốc phòng",
    "DVH": "Đất xây dựng cơ sở văn hóa",
    "DYT": "Đất xây dựng cơ sở y tế",
    "DRA": "Đất công trình xử lý chất thải",
    "DDD": "Đất có di tích lịch sử - văn hóa, danh lam thắng cảnh, di sản thiên nhiên",
    "CCC": "Đất sử dụng vào mục đích công cộng",
    "CAN": "Đất an ninh",
    "TON": "Đất tôn giáo",
    "TIN": "Đất tín ngưỡng",
    "SON": "Đất có mặt nước dạng sông, ngòi, kênh, rạch, suối",
    "MNC": "Đất có mặt nước chuyên dùng dạng ao, hồ, đầm, phá",
    "PNK": "Đất phi nông nghiệp khác",
    "DXH": "Đất xây dựng cơ sở xã hội",
    "DCH": "Đất chợ dân sinh, chợ đầu mối",
    "DTS": "Đất xây dựng trụ sở của tổ chức sự nghiệp",
    "DKH": "Đất xây dựng cơ sở khoa học và công nghệ",
    "DBV": "Đất công trình hạ tầng bưu chính, viễn thông, công nghệ thông tin",
}
PLAN_OUTLINE = {"color": "#ff0000", "width": 0.07 * 96 / 25.4, "dash": [4, 2]}

# Publish a field only after assigning it a meaningful label for its own layer.
LAYERS = {
    "lua-2030": {
        "source": "Lua2030.gpkg", "epsg": 5897,
        "label": "Đất lúa đến năm 2030", "short": "Lúa 2030", "group": "Đến năm 2030",
        "description": "Lớp đất lúa đến năm 2030 theo chỉ tiêu PA2030-IN.",
        "color": RICE_FILL, "kind": "polygon", "visible": True,
        "outline": {"color": "#ff0000", "width": 0.8, "overview_width": 0.2},
        "remove_overlaps": True,
        "fields": {
            "ten_xa_web": "Tên xã/phường",
            "dien_tich_web_ha": "Diện tích",
        },
        "search": ["ten_xa_web", "MaOBao"],
    },
    "chuyen-doi-2030": {
        "source": "ChuyenDoiLua2030.gpkg", "epsg": 5897,
        "label": "Chuyển đổi lúa đến năm 2030", "short": "Chuyển đổi lúa", "group": "Đến năm 2030",
        "description": "Năm nhóm màu theo mã loại đất HNK, CLN, NTS, CNT và NKH.",
        "color": CONVERSION_COLORS["CLN"], "kind": "polygon", "visible": False,
        "category_field": "ma_loai_dat", "categories": CONVERSION_COLORS, "outline": PLAN_OUTLINE,
        "source_fields": ["ma_loai_dat"],
        "fields": {
            "ten_xa_web": "Tên xã/phường",
            "muc_dich_web": "Mục đích chuyển đổi",
        },
        "search": ["ten_xa_web", "muc_dich_web", "ma_loai_dat"],
    },
    "phi-nn-2030": {
        "source": "PhiNN2030.gpkg", "epsg": 5897,
        "label": "Lúa chuyển sang phi nông nghiệp đến năm 2030", "short": "Sang phi nông nghiệp",
        "group": "Đến năm 2030", "description": "Phạm vi chuyển sang phi nông nghiệp theo lớp nguồn.",
        "color": "#ffa0aa", "kind": "polygon", "visible": False, "outline": PLAN_OUTLINE,
        "source_fields": ["maLoaiDat", "MaMau", "TenCtrinh"],
        "fields": {
            "ten_xa_web": "Tên xã/phường",
            "muc_dich_web": "Mục đích chuyển đổi",
        },
        "search": ["ten_xa_web", "muc_dich_web", "maLoaiDat", "MaMau", "TenCtrinh"],
    },
    "lua-kiem-ke": {
        "source": "LuaKiemKe.gpkg", "epsg": 3405,
        "label": "Hiện trạng lúa kiểm kê", "short": "Lúa kiểm kê", "group": "Hiện trạng",
        "description": "Các vùng mã LUC trong lớp dữ liệu kiểm kê được cung cấp.",
        "color": RICE_FILL, "kind": "polygon", "visible": False,
        "outline": {"color": "#6b8e00", "width": 0.65, "overview_width": 0.15},
        "source_fields": ["MaLD_HT"],
        "fields": {"ten_xa_web": "Tên xã/phường", "loai_dat_web": "Loại đất"},
        "search": ["ten_xa_web", "loai_dat_web", "MaLD_HT"],
    },
    "lua-thuc-te": {
        "source": "LuaThucTeSanXuat.gpkg", "epsg": 4326,
        "label": "Hiện trạng thực tế sản xuất lúa", "short": "Lúa thực tế", "group": "Hiện trạng",
        "description": "Phạm vi sản xuất lúa theo lớp dữ liệu thực tế được cung cấp.",
        "color": RICE_FILL, "kind": "polygon", "visible": False,
        "outline": {"color": "#1b7a43", "width": 0.75, "overview_width": 0.15, "dash": [3, 2]},
        "source_fields": ["tenXa", "MaOBao", "Xa__CU_", "HienTrang"],
        "fields": {
            "ten_xa_web": "Tên xã/phường",
            "dien_tich_xa_web": "Diện tích thực tế của xã/phường",
        },
        "search": ["ten_xa_web", "tenXa", "MaOBao", "Xa__CU_", "HienTrang"],
    },
    "ranh-tinh": {
        "source": "mau/data.zip", "member": "RanhTinh_3857", "epsg": 3857,
        "label": "Ranh tỉnh (tham chiếu từ mẫu)", "short": "Ranh tỉnh", "group": "Tham chiếu",
        "description": "Đường ranh từ ứng dụng mẫu.",
        "color": "#244f66", "kind": "line", "visible": True,
        "outline": {"color": "#244f66", "width": 2.4, "dash": [6, 2]},
        "fields": {}, "search": [],
    },
    "ranh-xa": {
        "source": "mau/data.zip", "member": "RanhXa_3857", "epsg": 3857,
        "label": "Ranh xã, phường (tham chiếu từ mẫu)", "short": "Ranh xã, phường",
        "group": "Tham chiếu", "description": "Ranh 102 đơn vị từ ứng dụng mẫu, phục vụ định vị.",
        "color": "#36596b", "kind": "boundary", "visible": True,
        "fields": {"TenXa": "Tên đơn vị trong mẫu"}, "search": ["TenXa"],
    },
}


def search_text(value):
    stripped = unicodedata.normalize("NFD", value.casefold().replace("đ", "d"))
    return " ".join("".join(char for char in stripped if not unicodedata.combining(char)).split())
