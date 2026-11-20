# Prompt bàn giao dự án WebGIS

Bạn đang tiếp nhận dự án WebGIS **Xác định vùng quy hoạch trồng lúa năng suất, chất lượng cao trên địa bàn tỉnh Đồng Tháp**. Đọc trạng thái dưới đây, đối chiếu với các tệp trong thư mục đã giải nén, rồi thực hiện yêu cầu tiếp theo của tôi. Giữ các chỉnh sửa mới của người dùng. Dùng tệp mẫu để tham khảo bố cục và ký hiệu theo phạm vi đã thống nhất.

## Mở dự án và xác định bản đang chạy

- Mở thư mục có `LopWebGis`, `mau`, `webgis` và hai tệp Excel. Đọc `webgis/README.md` và kiểm tra `webgis/var/catalog.json` trước khi thay đổi dữ liệu. Khi README có các phương án hạ tầng từ giai đoạn thiết kế, dùng cấu hình thực tế dưới đây làm mốc.
- Trang chính là [WebGIS Đồng Tháp](https://chuyendoiluadongthap.x10.mx/). Gói bàn giao này chứa bản frontend `webgis-ecf58075ca00`. Frontend là HTML, CSS và JavaScript dùng MapLibre GL, mã ở `webgis/static` và triển khai vào `public_html` trên x10Hosting. [DirectAdmin của dự án](https://x11.x10hosting.com:2222/evo/filemanager/files?path=/domains/chuyendoiluadongthap.x10.mx/public_html)
- Bản dữ liệu đang chạy là `cacf6f341dba457ba3967db5dd2ff031`. Cloudflare Workers Free phục vụ danh mục lớp và các phần PMTiles qua Static Assets. Worker `dong-thap-lua-webgis` dùng D1 `dong-thap-webgis-attributes` để trả dữ liệu thuộc tính và tìm kiếm. Duy trì cấu hình miễn phí hiện tại. Việc thay đổi dịch vụ, thanh toán hoặc quyền tài khoản cần chỉ đạo của tôi. [Danh mục lớp trực tuyến](https://dong-thap-lua-webgis.vietanhquyhoach.workers.dev/api/layers)
- Gói có mã nguồn, dữ liệu gốc, các bản dữ liệu đã xử lý trong `webgis/var`, tệp triển khai, thư viện Node hiện có trên Windows và công cụ cần thiết. Cache Wrangler và Python được tạo lại trên máy mới. Đăng nhập Cloudflare và DirectAdmin bằng phiên được cấp phép khi cần triển khai.

## Dữ liệu và giao diện cần bảo toàn

- Năm lớp nghiệp vụ gồm Đất lúa đến năm 2030, Chuyển đổi lúa đến năm 2030, Lúa chuyển sang phi nông nghiệp đến năm 2030, Hiện trạng lúa kiểm kê và Hiện trạng thực tế sản xuất lúa. Hai lớp ranh dùng để định vị là Ranh tỉnh và Ranh xã, phường. Các GeoPackage nguồn nằm trong `LopWebGis`, ranh tham chiếu lấy từ `mau/data.zip`.
- Lớp Lúa 2030 đã xử lý chồng đè và cắt bỏ vùng của xã/phường được giao 0 ha. Chỉ tiêu lấy từ cột F của sheet `PA2030-IN` trong `SL-CHUYEN DOI LUA-DONGTHAP-T11-2026-v1.xlsx`. Popup có ID, Tên xã/phường, Diện tích. Làm tròn đến 0,01 ha. Tổng các phần theo xã/phường phải khớp dòng chỉ tiêu tương ứng. Tổng các dòng đã làm tròn của 102 đơn vị là 177.146,56 ha. Tách rõ số chỉ tiêu hiển thị và diện tích đo từ hình học khi đối chiếu.
- Popup lớp Chuyển đổi lúa và Phi nông nghiệp dùng ID, Tên xã/phường, Mục đích chuyển đổi. Lớp Lúa kiểm kê dùng ID, Tên xã/phường, Loại đất. Lớp thực tế sản xuất dùng ID, Tên xã/phường, Diện tích thực tế của xã/phường. Diện tích thực tế lấy theo cột F sheet `danh gia tieu chi-o bao-moi` trong `theoOBaoThuyLoiThanhRynan.xlsx`. Lấy số tổng hợp cấp xã/phường theo bảng này.
- Giao diện dùng nguyên ảnh logo Sub-NIAPP từ `logo.png` trên đầu trang nền sáng. Phần trên ghi “Tỉnh Đồng Tháp · Hệ thống thông tin địa lý”. Danh sách lớp và chú giải bỏ cột số lượng. Lúa 2030 chỉ tô vùng. Ranh xã/phường phải dễ phân biệt. Chú giải Chuyển đổi lúa chỉ hiển thị nhóm có dữ liệu, hiện gồm HNK, CLN, NTS và CNT. Thanh Độ trong suốt mặc định 25%, giá trị tăng thì màu tô nhạt đi. Menu nền dùng tên Bản đồ đường, Bản đồ vệ tinh và Nền trống. Giữ ghi công nguồn bản đồ ở góc bản đồ.

## Quy trình tiếp tục

**Chạy tại máy**. Mở PowerShell tại thư mục `webgis`. Dự án đã chạy với Python 3.13 và Node.js 24. Cài các thư viện Python từ `requirements.txt`. Nếu chuyển máy, chạy `npm.cmd ci` cho frontend và `npm.cmd --prefix deploy ci` cho công cụ đóng gói. Trên Linux hoặc macOS dùng `npm` thay cho `npm.cmd`. Có thể chạy ngay từ bộ dữ liệu đã chuẩn bị bằng lệnh sau.

```powershell
python -X utf8 -m uvicorn server:app --host 127.0.0.1 --port 8765
```

**Sửa giao diện**. Sửa tại `webgis/static`. Chuẩn bị gói trỏ về backend đang chạy bằng các lệnh sau, vẫn từ thư mục `webgis`.

```powershell
$version = (Get-Content var/catalog.json -Encoding utf8 -Raw | ConvertFrom-Json).version
$release = "var/deployment/$version"
python -X utf8 deploy/prepare.py --frontend-only --api-origin 'https://dong-thap-lua-webgis.vietanhquyhoach.workers.dev'
```

Nếu bộ phát hành thiếu `pmtiles-client.mjs` nhưng đã có `cloudflare-worker-data.json`, chạy `node deploy/bundle.mjs $release` sau khi cài gói npm của `deploy`. Trong DirectAdmin, giải nén `frontend-assets.zip` vào `public_html`. Mở thử URL có thư mục phiên bản mà lệnh đóng gói in ra. Khi bản thử hoạt động, sao lưu trang chủ và dùng tệp `$release/index.html` để cập nhật `public_html/index.html`. HTML trong `webgis/static` dành cho máy cục bộ và cần qua bước đóng gói để có địa chỉ API Cloudflare và đường dẫn CSS/JavaScript theo phiên bản trên hosting.

**Sửa dữ liệu**. Kiểm tra đúng tệp nguồn và dùng các chế độ cập nhật của `build_data.py` theo README. Bảo toàn dữ liệu gốc. Đối soát đầu ra trước khi đóng gói. Khi có yêu cầu đưa dữ liệu mới lên, chuẩn bị lại gói Cloudflare và cấu hình phát hành từ `deploy/prepare.py` và `deploy/bundle.mjs`, nhập `attributes.sql` vào D1, kiểm tra API và triển khai Static Assets theo đúng tài khoản của dự án. Các thư mục phiên bản cũ trong `webgis/var` dùng cho đối chiếu và khôi phục. Danh mục `webgis/var/catalog.json` chỉ ra thư mục đang dùng ở bản cục bộ.

**Kiểm tra sau mỗi thay đổi**. Xác nhận đúng phiên bản tại trang chủ, tải được CSS/JS, logo, danh mục lớp và ô vector. Thử bật 5 lớp nghiệp vụ và 2 lớp ranh, kiểm tra tìm theo tên/ID và popup. Mẫu đối chiếu phiên bản hiện tại là Lúa 2030 `#19578`, Xã Tân Thành, `0,01 ha`. Với thay đổi dữ liệu 2030, kiểm tra lại các xã/phường có chỉ tiêu bằng 0 và tổng theo từng đơn vị. Chỉ báo đã triển khai sau khi xác minh trên địa chỉ chính thức.

**Yêu cầu tiếp theo của tôi**

[Dán nội dung cần làm tiếp vào đây.]
