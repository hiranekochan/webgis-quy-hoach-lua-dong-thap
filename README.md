# Xác định vùng quy hoạch trồng lúa năng suất, chất lượng cao trên địa bàn tỉnh Đồng Tháp

[Mở WebGIS](https://chuyendoiluadongthap.x10.mx/) · [Hướng dẫn phát triển và triển khai](webgis/README.md) · [Prompt bàn giao](PROMPT_BAN_GIAO.md)

`webgis` chứa giao diện MapLibre, máy chủ FastAPI dùng cục bộ, mã xử lý dữ liệu và cấu hình đóng gói để phát hành lên x10Hosting và Cloudflare Workers. `LopWebGis` chứa các lớp GeoPackage nguồn. Hai tệp Excel ở thư mục gốc dùng để đối chiếu chỉ tiêu lúa giữ lại và diện tích thực tế. `mau` chứa bản đồ mẫu và dữ liệu ranh tham chiếu.

Các bộ dữ liệu đã xử lý và tệp triển khai được lưu trong [bản bàn giao tải xuống từ Releases](https://github.com/hiranekochan/webgis-quy-hoach-lua-dong-thap/releases/tag/ban-giao-2026-11-19). Có thể dùng `webgis/var` từ bản bàn giao để chạy với dữ liệu đã chuẩn bị, hoặc tạo lại dữ liệu theo hướng dẫn trong `webgis/README.md`.
