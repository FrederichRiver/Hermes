from qts.utils import parser


def test_extract_codes_shanghai():
    sample = "公司示例 600000 600001 600002 其他 600000"
    res = parser.extract_codes_from_text(sample, "SH")
    assert res == ["SH600000", "SH600001", "SH600002"]


def test_normalize_code():
    assert parser.normalize_code("6001", "SH") == "SH006001"
    assert parser.normalize_code("sz000001", "SZ") == "SZ000001"
