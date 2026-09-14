"""P1-05 字段脱敏（PII masking）测试。"""

from core.ai_privacy import mask_pii_text


def test_mask_email():
    assert mask_pii_text("联系 zhang.san@example.com 获取") == "联系 <邮箱> 获取"


def test_mask_phone():
    assert mask_pii_text("电话 13812345678") == "电话 <手机号>"
    # 长数字不误伤
    assert mask_pii_text("编号 11381234567890") == "编号 11381234567890"


def test_mask_idcard():
    assert mask_pii_text("身份证 110101199003077758") == "身份证 <身份证>"
    # 含校验位 X
    assert mask_pii_text("11010119900307775X") == "<身份证>"


def test_mask_mixed_and_path_preserved():
    text = r"C:\Users\alice\文档\报告2024.docx 里写了 bob@test.com，手机 13998765432"
    out = mask_pii_text(text)
    assert r"C:\Users\alice\文档\报告2024.docx" in out  # 路径不脱敏
    assert "bob@test.com" not in out
    assert "13998765432" not in out


def test_empty_text():
    assert mask_pii_text("") == ""
    assert mask_pii_text(None) is None
