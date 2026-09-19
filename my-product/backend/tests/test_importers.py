from openpyxl import Workbook
import pytest

from app.importers import EXPECTED_HEADERS, normalize_cas, read_pollutant_workbook


@pytest.mark.parametrize(("source", "expected"), [
    ("75-05-08，", "75-05-8"),
    ("，75/9/2", "75-09-2"),
    ("79/10/7，", "79-10-7"),
    (" ，79/01/6", "79-01-6"),
])
def test_normalize_cas_repairs_source_formatting(source: str, expected: str) -> None:
    assert normalize_cas(source) == expected


def test_normalize_cas_rejects_invalid_checksum() -> None:
    with pytest.raises(ValueError, match="校验位"):
        normalize_cas("50-00-1")


def test_read_workbook_merges_duplicate_cas_as_aliases(tmp_path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append([None, *EXPECTED_HEADERS])
    sheet.append([1, "均三甲苯", "Mesitylene", "C₆H₃(CH₃)₃", "C₉H₁₂", "108-67-8", 164.7, 120.19])
    sheet.append([2, "1,3,5-三甲苯", "Trimethylbenzene (1,3,5-)", "C₆H₃(CH₃)₃", "C₉H₁₂", "108-67-8", 164.7, 120.19])
    sheet.append([None, "这是一行说明文字", None, None, None, None, None, None])
    source = tmp_path / "pollutants.xlsx"
    workbook.save(source)

    rows, metadata = read_pollutant_workbook(source)

    assert metadata["totalRows"] == 2
    assert metadata["uniqueRows"] == 1
    assert metadata["duplicateRows"] == 1
    assert rows[0].aliases == ["1,3,5-三甲苯", "Trimethylbenzene (1,3,5-)"]
