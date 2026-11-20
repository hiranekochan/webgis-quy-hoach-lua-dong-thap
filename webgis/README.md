# Xác định vùng quy hoạch trồng lúa năng suất, chất lượng cao trên địa bàn tỉnh Đồng Tháp

## Chạy trên máy

Lệnh dưới đây chạy từ thư mục `webgis`. Giữ `LopWebGis` và `mau` cùng cấp với thư mục này.

```powershell
python -m pip install -r requirements.txt
npm.cmd ci
python -X utf8 build_data.py
python -X utf8 -m uvicorn server:app --host 127.0.0.1 --port 8765
```

Mở [WebGIS](http://127.0.0.1:8765/) hoặc [tài liệu API](http://127.0.0.1:8765/docs). Nếu `var/catalog.json` đã có cùng thư mục dữ liệu mang mã phiên bản, có thể khởi động ngay bằng lệnh cuối. Sau khi cập nhật nguồn, chạy lại `build_data.py` rồi khởi động lại máy chủ để dùng phiên bản mới. Chọn nền trống để sử dụng lớp chuyên đề khi ngoại tuyến.

Nếu chỉ cập nhật lớp Lúa 2030 và đã có một phiên bản dữ liệu, chạy `python -X utf8 build_data.py --refresh-lua-2030`. Lệnh tạo ô và bản tra cứu mới cho lớp này, đồng thời tái sử dụng dữ liệu công bố của các lớp khác.

Khi chỉ thay bảng chỉ tiêu PA2030-IN, chạy `python -X utf8 build_data.py --apply-pa2030` để dùng lại hình học đã xử lý chồng đè. Đặt workbook `SL-CHUYEN DOI LUA-DONGTHAP-T11-2026-v1.xlsx` ở thư mục gốc của dự án và khởi động lại máy chủ sau khi tạo dữ liệu.

Giao diện hỗ trợ bật chồng lớp, chỉnh độ đậm, xem thuộc tính tại điểm chọn, tìm tên xã/mã ô bao/mã đất, tìm tọa độ, định vị và đo tham khảo. Có thể nhập `#16403` để tìm theo ID nguồn và giới hạn kết quả theo lớp. Khi các vùng hiển thị chồng nhau, khung thuộc tính cho phép chọn từng đối tượng.

## Bản trực tuyến

Giao diện chạy tại [WebGIS Đồng Tháp](https://chuyendoiluadongthap.x10.mx/). Cloudflare Workers Free phục vụ các phần PMTiles qua Static Assets và dùng D1 cho API thuộc tính. Danh mục lớp và ô bản đồ đi qua Static Assets để phần bản đồ vẫn tải khi API tra cứu hết hạn mức.

Khi có bộ dữ liệu mới, chạy các lệnh sau từ thư mục `webgis`. `$pmtilesExe` là đường dẫn đến công cụ Protomaps PMTiles và `$databaseId` là ID của cơ sở dữ liệu `dong-thap-webgis-attributes` trong tài khoản Cloudflare.

```powershell
npm.cmd --prefix deploy ci
$version = (Get-Content var/catalog.json -Encoding utf8 -Raw | ConvertFrom-Json).version
$release = "var/deployment/$version"
python -X utf8 deploy/prepare.py --pmtiles $pmtilesExe --database-id $databaseId
node deploy/bundle.mjs $release
python -X utf8 deploy/prepare.py --frontend-only --api-origin 'https://dong-thap-lua-webgis.vietanhquyhoach.workers.dev'
& deploy/node_modules/.bin/wrangler.cmd d1 execute dong-thap-webgis-attributes --remote --file "$release/attributes.sql" --config "$release/wrangler.json"
& deploy/node_modules/.bin/wrangler.cmd deploy --config "$release/wrangler.json"
```

Trên DirectAdmin, giải nén `frontend-assets.zip` vào `public_html`. Kiểm tra thư mục giao diện theo mã phiên bản trước khi cập nhật `public_html/index.html` bằng tệp `index.html` cùng bộ xuất.

## Dữ liệu và nhóm lớp

| Nhóm | Tệp | Đối tượng | CRS nguồn | Khóa tra cứu và cách sử dụng |
|---|---|---:|---|---|
| Đến 2030 | `Lua2030.gpkg` | 24.686 | EPSG:5897 | WebGIS hiển thị bản đã xử lý chồng đè, cắt theo ranh xã và áp chỉ tiêu PA2030-IN. Bảng tra cứu gồm ID, Tên xã/phường và Diện tích. |
| Đến 2030 | `ChuyenDoiLua2030.gpkg` | 11.972 | EPSG:5897 | Vẽ theo `ma_loai_dat`. Bảng tra cứu gồm ID, Tên xã/phường và Mục đích chuyển đổi. |
| Đến 2030 | `PhiNN2030.gpkg` | 27.710 | EPSG:5897 | Tra ID, Tên xã/phường và Mục đích chuyển đổi. |
| Hiện trạng | `LuaKiemKe.gpkg` | 18.238 | EPSG:3405 | Tra ID, Tên xã/phường và Loại đất. Nguồn dùng mã `LUC` cho toàn bộ vùng. |
| Hiện trạng | `LuaThucTeSanXuat.gpkg` | 18.844 | EPSG:4326 | Tra ID, Tên xã/phường và Diện tích thực tế của xã/phường theo bảng Excel. |

Tổng cộng **101.450 đối tượng nghiệp vụ** trong khoảng **211,57 MB** GeoPackage nguồn. Ranh tỉnh và ranh 102 xã, phường lấy từ `mau/data.zip` để định vị và tìm tên xã. Cần đối chiếu với bộ ranh hành chính được xác nhận trước khi tính diện tích theo xã. Khung nhìn mặc định mở lớp lúa 2030 cùng ranh tỉnh và ranh xã, phường. Ranh xã có nét xanh đậm với viền trắng để dễ nhận biết trên các lớp chuyên đề.

`tenXa` và `ten_ranh` có bản ghi trống và tên chứa dấu `?` trong nguồn. Dữ liệu tên xã từ bộ ranh mẫu có thể tìm có dấu hoặc không dấu. Cột `area` của lớp kiểm kê trống cả 18.238 bản ghi. Các cột `DienTich`, `area`, `dien_tich_ha` có phạm vi điền dữ liệu khác nhau. Giai đoạn này hiển thị thuộc tính có nhãn phù hợp từng lớp, chưa tổng hợp diện tích hoặc tính mức chênh lệch.

### Ký hiệu QGIS

Lấy màu ba lớp 2030 từ `Ban Do/0_Final/BaoCaoThucTe/BaoCao.qgz` trong thư mục `CD LUA`. Mã SHA-256 của ba tệp lớp 2030 được dự án QGIS tham chiếu trùng với các bản sao trong `LopWebGis`. Lấy màu hai lớp hiện trạng từ `layer_styles` trong GeoPackage tương ứng. Lúa 2030, kiểm kê và thực tế cùng dùng màu tô `#E6FF00`. Riêng Lúa 2030 có viền đỏ liền nét trong WebGIS. Phi nông nghiệp dùng `#FFA0AA`. Lớp lúa 2030 bỏ hai trường `LoaiHinh` và `DeXuat` khỏi khung tra cứu vì chúng chứa mô tả lúa chất lượng cao.

| Mã chuyển đổi | Màu tô QGIS | Bản ghi nguồn có đúng mã |
|---|---|---:|
| HNK | `#FFF0B4` | 347 |
| CLN | `#FFD2A0` | 10.988 |
| NTS | `#AAFFFF` | 621 |
| CNT | `#E6E682` | 3 |
| NKH | `#F5FFB4` | 0 |

Bốn bản ghi mã ghép và chín bản ghi thiếu mã vẫn tra được thuộc tính. Các bản ghi đó nằm ngoài bộ ô hiển thị chuyên đề chuyển đổi. Giao diện lấy cách bố trí nút mở bảng lớp, bảng tìm kiếm và khung thông tin từ mẫu `mau/AnGiang.html`.

Lớp chuyển đổi lấy tên xã/phường từ lớp ranh tham chiếu. Với vùng cắt qua ranh, bảng tra cứu dùng tên đơn vị có phần giao lớn nhất. Tên mục đích theo phân loại đất tại Điều 9 Luật Đất đai. Có thể cập nhật riêng thuộc tính bằng `python -X utf8 build_data.py --refresh-conversion-fields` và khởi động lại máy chủ. [Luật Đất đai](https://vbpl.vn/FileData/TW/Lists/vbpq/Attachments/177815/VanBanGoc_31-2024-qh15_1.pdf)

### Xử lý chồng đè lớp Lúa 2030

Mạng biên được chia thành các vùng không chồng nhau trong EPSG:5897 trên lưới 1 mm. Mỗi vùng chỉ gán cho một ID nguồn. Thứ tự ưu tiên là bản cập nhật Tân Thạnh theo metadata, sau đó đến các bản ghi đất lúa tổng hợp từ `EraseDongThap` và `EraseTienGiang`, rồi các bản ghi còn lại. Khi hai bản ghi cùng mức ưu tiên, vùng giao thuộc về ID nguồn nhỏ hơn. ID của các đối tượng còn hình học được giữ để tra cứu.

Kết quả `Lua2030_KhongChongDe.gpkg` và biên bản kiểm tra `lua-2030-topology.json` nằm trong thư mục phiên bản đang dùng dưới `var`. Trường `dien_tich_ha` thể hiện diện tích hình học đã xử lý. Trường `dien_tich_ha_nguon` giữ số gốc để đối chiếu. Phép kiểm tra topology áp dụng trong nội bộ lớp Lúa 2030. Giao cắt giữa các lớp nghiệp vụ vẫn có thể xuất hiện khi bật chồng lớp.

Tổng diện tích từng bản ghi nguồn là 295.006,0317 ha. Hợp vùng nguồn trên lưới xử lý cho 171.244,3579 ha, với 123.761,6802 ha tính lặp khi cộng các vùng trên cùng lưới. Bản đã xử lý còn 20.387 đối tượng, có tổng diện tích 171.244,3572 ha. Sai khác phạm vi phủ theo phép hiệu đối xứng trên lưới 1 mm là 6,1635 m². Kiểm tra trên tệp xuất xác nhận không còn cặp đa giác giao nhau có diện tích. Một số cạnh chung vẫn khác cách chia đỉnh.

### Chỉ tiêu lúa giữ lại theo xã, phường

Lấy tên tại cột B và diện tích tại cột F của 102 dòng xã/phường trong sheet `PA2030-IN`. Đối chiếu tên có dấu với lớp ranh tham chiếu. Dùng tên **Phường Sơn Qui** theo bảng Excel cho **Phường Sơn Quy** trong lớp ranh. Các vùng bị cắt theo ranh của 71 đơn vị giao chỉ tiêu dương. Vùng ở đơn vị giao 0 ha và phần ngoài ranh xã tham chiếu được loại khỏi lớp hiển thị. Đã loại khoảng 713,17 ha trong các đơn vị giao 0 ha và 22,65 ha nằm ngoài bộ ranh. Bản đồ sau cắt có khoảng 170.508,54 ha hình học.

Diện tích trong bảng tra cứu được phân bổ theo tỷ trọng diện tích hình học của các phần trong cùng xã/phường. Phần lẻ được phân bổ ở đơn vị 0,01 ha để tổng các giá trị hiển thị khớp chỉ tiêu của từng đơn vị. Tổng 102 dòng đã làm tròn là **177.146,56 ha**. Ô tổng tỉnh F11 làm tròn là **177.146,54 ha**. Số hiển thị phản ánh chỉ tiêu Excel, còn diện tích hình học phản ánh vùng thể hiện trên bản đồ. Tệp hình học `Lua2030_PA2030.gpkg` và đối chiếu theo xã `lua-2030-pa2030.json` nằm trong thư mục phiên bản.

### Tra cứu phi nông nghiệp, kiểm kê và thực tế sản xuất

Tên xã/phường lấy theo đơn vị có phần giao lớn nhất với hình học. Lớp phi nông nghiệp hiển thị tên loại đất ứng với mã đích chính. Với mã ghép, dùng phần trước dấu ngoặc. Khi mã đích trống thì dùng mã ký hiệu. Trường hợp hai mã mâu thuẫn hoặc đều thiếu hiển thị `Chưa xác định`. Mã kiểm kê `LUC` hiển thị là **Đất chuyên trồng lúa**. [Bảng mã loại đất trong Thông tư 29/2024/TT-BTNMT](https://vbpl.vn/FileData/TW/Lists/vbpq/Attachments/173536/VanBanGoc_TT%2029-2024-TT-BTNMT_Signed-quy%20%C4%91%E1%BB%8Bnh%20k%E1%BB%B9%20thu%E1%BA%ADt%20l%E1%BA%ADp%2C%20%C4%91i%E1%BB%81u%20ch%E1%BB%89nh%20QH%2C%20KHSD%C4%90.pdf) · [Bảng mã lịch sử có DTS](https://qppl.dienbien.gov.vn/qlvb/vbpq.nsf/str/282E5DCF5937FB75472587F800052249/%24file/dongdau949_28-02-2022-16-47-25_03-vbhn-btnmt_Signed.pdf)

Lớp thực tế sản xuất đọc cột F **Diện tích Thực tế / HT 2024 (ha)** của sheet `danh gia tieu chi-o bao-moi` trong `theoOBaoThuyLoiThanhRynan.xlsx`. Số hiển thị là số tổng hợp của xã/phường và được làm tròn đến hai chữ số thập phân. Các ô bao trong Excel dùng tên mô tả, còn GeoPackage dùng mã RNOB. Các xã/phường thiếu dòng tổng trong Excel hiển thị `Chưa có số liệu`. Có thể cập nhật ba bảng tra cứu bằng `python -X utf8 build_data.py --refresh-detail-fields phi-nn-2030 lua-kiem-ke lua-thuc-te` rồi khởi động lại máy chủ.

### Bản đồ nền

Google Maps là nền đường mặc định, sử dụng địa chỉ XYZ từ mẫu `mau/AnGiang.html`. Có thể chọn ảnh vệ tinh Esri hoặc nền trống trong bảng lớp. Trình duyệt tải ô nền theo vùng nhìn và hiển thị ghi nguồn của nhà cung cấp. [Esri World Imagery](https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer)

## Kiến trúc bản chạy hiện tại

```text
GeoPackage nguồn + ranh mẫu
          │
          ▼
Kiểm tra CRS và hình học → phiên bản dữ liệu có SHA-256 nguồn
          ├── MBTiles chứa ô MVT theo lớp → FastAPI /tiles → MapLibre GL JS
          └── SQLite chỉ mục FTS5        → FastAPI /features, /search → Khung tra cứu
```

- GDAL tạo ô vector sẵn theo vùng nhìn và mức thu phóng. Ô chứa hình học hiển thị và ID nguồn. Khi người dùng chọn đối tượng, API trả thuộc tính của đối tượng đó từ SQLite. Có giới hạn kết quả tra cứu và cache ô theo phiên bản dữ liệu.
- Phép chuyển đổi từ EPSG:5897 và EPSG:3405 dùng PROJ, yêu cầu phép biến đổi có sẵn và loại phép ước lượng ballpark. Bản hiển thị được xử lý trong EPSG:3857, gồm kiểm tra hợp lệ, sửa hình học khi cần và đưa lên lưới 1 mm trước khi cắt ô. Tệp nguồn và giá trị thuộc tính được giữ nguyên. Hình học ô có lượng tử hóa theo mức thu phóng.
- Phiên bản dữ liệu ghi nhận mã băm, số đối tượng nguồn, số hình học trước khi cắt ô, số hình học lỗi ở nguồn và số cần sửa ở hệ hiển thị. API được cố định vào một phiên bản trong suốt thời gian chạy, tránh trộn ô và thuộc tính giữa hai lần nhập.
- Mẫu cũ dùng `fetch → shp.parseZip → L.geoJSON` và đọc MBTiles qua SQL.js. Cấu hình mở mặc định `QuyHoachCLC_3857.zip` nhưng tệp đó không có trong gói. Bản này giữ tương tác chính của mẫu, chỉ tải ô trong vùng đang xem và tìm trên dữ liệu dự án thay cho gọi Nominatim công cộng theo phím gõ. [Chính sách Nominatim](https://operations.osmfoundation.org/policies/nominatim/)

Các tuyến API nghiệp vụ gồm `GET /api/layers`, `GET /api/{version}/tiles/{layer}/{z}/{x}/{y}.pbf`, `GET /api/{version}/features/{layer}/{fid}` và `GET /api/{version}/search?q=…&layer=…`. Máy chủ chạy tại loopback và phục vụ bản xem nội bộ.

### Kết quả kiểm tra dữ liệu hiển thị

Đã đối chiếu mã băm nguồn, số bản ghi, truy vấn thuộc tính và ô tải qua API. Phiên bản cập nhật Lúa 2030 giữ nguyên các ô và bản ghi tra cứu của sáu lớp còn lại. Bộ MBTiles gồm 324.219 ô từ zoom 7 đến 17, dung lượng khoảng 168,18 MB cho hai lớp tham chiếu và năm lớp nghiệp vụ.

| Lớp nghiệp vụ | ID trong phiên bản WebGIS | ID xuất hiện trong ô tại zoom 17 |
|---|---:|---:|
| Đất lúa đến năm 2030 | 20.626 | 20.022 |
| Chuyển đổi lúa đến năm 2030 | 11.972 | 11.726 |
| Lúa chuyển sang phi nông nghiệp đến năm 2030 | 27.710 | 27.212 |
| Hiện trạng lúa kiểm kê | 18.238 | 18.238 |
| Hiện trạng thực tế sản xuất lúa | 18.844 | 18.763 |
| Tổng | 97.390 | 95.961 |

Ô bản đồ ở zoom 17 lược bớt một số hình học nhỏ hoặc rất mảnh. Mười ba bản ghi chuyển đổi ngoài danh mục màu cũng không xuất hiện trong ô. Các ID vẫn tra được theo phạm vi bản ghi của phiên bản WebGIS. Khi giao cắt hoặc tính diện tích Lúa 2030, dùng hình học đã xử lý trong GeoPackage.

## Các phương án backend miễn phí

Hạn mức đối chiếu ngày **18/11/2026**.

| Nhu cầu | Phương án | Hạn mức và điểm cần kiểm tra |
|---|---|---|
| Xem và tra cứu nội bộ ngay | **FastAPI + SQLite FTS5 + MBTiles** trên máy hiện có | Bản chạy đi kèm. Phù hợp với bộ dữ liệu cập nhật theo đợt và ít người đồng thời. Khi đưa lên LAN, thêm HTTPS qua reverse proxy và xác thực theo cơ chế của cơ quan. Máy chủ phải bật để truy cập. |
| Tra cứu trên Internet, có ít hoặc không có người biên tập | **Cloudflare Pages + R2 Standard (PMTiles) + Workers API + Neon/PostGIS** | Pages chứa giao diện, mỗi asset tối đa 25 MiB. R2 Standard có 10 GB-tháng, 1 triệu thao tác ghi loại A và 10 triệu thao tác đọc loại B mỗi tháng trong gói miễn phí, miễn phí lưu lượng truyền ra Internet. R2 có thể phát sinh phí vượt hạn mức. Workers Free có 100.000 yêu cầu/ngày và 10 ms CPU/yêu cầu. Dùng R2 phục vụ ô đã tạo, để Workers xử lý yêu cầu tra cứu ngắn và PostGIS xử lý truy vấn không gian. [Pages](https://developers.cloudflare.com/pages/platform/limits/) · [R2](https://developers.cloudflare.com/r2/pricing/) · [Workers](https://developers.cloudflare.com/workers/platform/limits/) · [PMTiles và HTTP Range](https://docs.protomaps.com/pmtiles/cloud-storage) |
| Cơ sở dữ liệu không gian quản lý trên cloud | **Neon Free + PostGIS** | 1 GB dữ liệu PostgreSQL, 100 CU-giờ và 5 GB truyền ra mỗi tháng trên mỗi dự án theo bảng giá hiện tại. Phù hợp nếu ưu tiên dư địa cơ sở dữ liệu. Có độ trễ đánh thức khi compute về 0 và giới hạn truy cập khi vượt hạn mức kỳ. [Giá Neon](https://neon.com/pricing) · [PostGIS trên Neon](https://neon.com/docs/extensions/postgis) |
| Cần tài khoản và phân quyền biên tập sớm | **Supabase Free + PostGIS + Auth/RLS** | 500 MB mỗi cơ sở dữ liệu, 5 GB truyền ra không qua cache và 5 GB qua cache theo tháng. Dự án Free có thể bị tạm dừng sau một tuần ít hoạt động. Nên dùng R2 cho ô hiển thị và đo dung lượng sau nhập trước khi chốt Supabase. [Giá Supabase](https://supabase.com/pricing) · [Băng thông](https://supabase.com/docs/guides/platform/manage-your-usage/egress) · [PostGIS trên Supabase](https://supabase.com/docs/guides/database/extensions/postgis) |
| Xử lý không gian tập trung trong mạng cơ quan | **PostgreSQL/PostGIS + Martin + FastAPI**, trên máy chủ có sẵn | Phần mềm nguồn mở. Martin cấp ô từ PostGIS hoặc MBTiles/PMTiles. Phù hợp khi ô cần phản ánh cập nhật nhanh, chất lượng dịch vụ do cơ quan vận hành. Chi phí phụ thuộc hạ tầng, sao lưu và người vận hành. [Martin](https://maplibre.org/martin/) |

**Nên thí điểm nội bộ bằng bản đang chạy.** Nếu chủ dữ liệu duyệt mở tra cứu trên Internet, chọn **Cloudflare Pages + R2 Standard + Workers API + Neon/PostGIS**. Giữ hình học và thuộc tính chi tiết trong PostGIS, tách ô hiển thị sang R2 và kết nối Workers đến Neon qua driver HTTP. Bật R2 cần đăng ký dịch vụ qua bước thanh toán của Cloudflare. Nếu xác định có biên tập và phân quyền ngay từ đợt đầu, cân nhắc Supabase sau khi đo thử dung lượng thật. Cần đo lại dung lượng PostgreSQL sau khi thêm bảng, chỉ mục GiST và các phiên bản. [Neon serverless driver](https://neon.com/docs/serverless/serverless-driver) · [Đăng ký R2](https://developers.cloudflare.com/r2/get-started/)

## Các bước phát triển tiếp

1. **Chốt bộ dữ liệu xuất bản.** Ghi kỳ kiểm kê, thời điểm/phương pháp xác định sản xuất thực tế, nguồn pháp lý của từng lớp đến 2030, lớp ranh hành chính chuẩn và danh sách thuộc tính được phép hiển thị. Chuẩn hóa mã xã qua bảng đối chiếu do chủ dữ liệu xác nhận. Kiểm tra đối chiếu CRS với điểm hoặc ranh đã biết.
2. **Chuyển truy vấn sang PostGIS khi cần.** Lưu bảng nguồn theo đợt, danh mục phiên bản và năm bảng nghiệp vụ, khóa truy xuất `(version, layer, source_fid)`. Thêm mã xã chuẩn, mã chuyên đề chuẩn, chỉ mục GiST và chỉ mục tra cứu thuộc tính. Chạy thử nhập, đo `pg_total_relation_size`, kiểm tra truy vấn đại diện và tính cả dung lượng để giữ các phiên bản.
3. **Đối soát hiện trạng bằng giao cắt hình học.** Dùng hình học đã kiểm định, hệ chiếu tính diện tích đã thống nhất và ranh xã đã duyệt. Hợp nhất vùng trùng trong từng lớp, sau đó tính phần giao và phần chỉ có ở từng lớp. Tổng hợp diện tích theo xã từ kết quả giao cắt, lưu cùng phiên bản và quy tắc làm tròn. Phân tích riêng các vùng chồng giữa lớp chuyển đổi lúa và phi nông nghiệp trước khi cộng số liệu. [PostGIS ST_Intersection](https://postgis.net/docs/ST_Intersection.html)
4. **Đưa vào vận hành.** Chuyển MBTiles sang PMTiles theo phiên bản nếu chọn R2 và kiểm tra HTTP Range/CORS. Dùng API đọc giới hạn thuộc tính, kiểm thử phân quyền và thử khôi phục sao lưu. Kiểm thử kích thước ô, thời gian mở bản đồ, truy vấn tại vị trí chồng lớp, mức dùng tài nguyên và khả năng chịu hạn mức. Chọn lại dịch vụ nền nếu dự kiến sử dụng công cộng với lưu lượng lớn.
