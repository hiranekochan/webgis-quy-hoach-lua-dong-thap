"""Read reported actual rice production totals at commune level."""

from contextlib import closing
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from io import BytesIO

from openpyxl import load_workbook

from layers import search_text
from lua2030_pa import commune_key


WORKBOOK = "theoOBaoThuyLoiThanhRynan.xlsx"
SHEET = "danh gia tieu chi-o bao-moi"


def read_actual_areas(path):
    content = path.read_bytes()
    result = {}
    with closing(load_workbook(BytesIO(content), read_only=True, data_only=True)) as book:
        sheet = book[SHEET]
        if search_text(sheet["F3"].value or "") != "dien tich thuc te / ht 2024 (ha)":
            raise ValueError("Không tìm thấy cột diện tích thực tế năm 2024 tại F3.")
        for row, (number, name, locality, _, _, area) in enumerate(
            sheet.iter_rows(min_row=5, max_col=6, values_only=True), 5
        ):
            # Detail rows have a locality in column C and must not be counted again.
            if locality or not str(number).strip().isdecimal():
                continue
            if not isinstance(name, str) or not isinstance(area, (int, float)) or area < 0:
                raise ValueError(f"Dòng tổng diện tích thực tế tại F{row} không hợp lệ.")
            key = commune_key(name)
            if key in result:
                raise ValueError(f"Trùng dòng tổng diện tích thực tế cho {name}.")
            result[key] = float(Decimal(str(area)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    return result, {"workbook": path.name, "sheet": SHEET, "column": "F",
                    "sha256": hashlib.sha256(content).hexdigest(), "communes": len(result)}
