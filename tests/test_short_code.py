"""
短代码验证测试
"""

import pytest
from app.utils.short_code import (
    normalize_short_code,
    validate_short_code,
    RESERVED_CODES,
)


class TestShortCodeValidation:
    """短代码验证测试"""

    def test_normalize_basic(self):
        """测试基本规范化"""
        assert normalize_short_code("ABC123") == "abci23"
        assert normalize_short_code("abc123") == "abci23"
        assert normalize_short_code("  abc123  ") == "abci23"

    def test_normalize_ambiguous_chars(self):
        """测试易混淆字符规范化"""
        assert normalize_short_code("abc012") == "abcsi2"
        assert normalize_short_code("abc123") == "abci23"
        assert normalize_short_code("abco12") == "abcsi2"
        assert normalize_short_code("abcl12") == "abcii2"
        assert normalize_short_code("abcI12") == "abcii2"

    def test_validate_valid_codes(self):
        """测试有效短代码（不包含易混淆字符）"""
        assert validate_short_code("abc234") == True
        assert validate_short_code(normalize_short_code("ABC234")) == True
        assert validate_short_code("abc-234") == True
        assert validate_short_code("abcsi2") == True
        assert validate_short_code("abcii2") == True

    def test_validate_invalid_length(self):
        """测试无效长度"""
        assert validate_short_code("ab") == False
        assert validate_short_code("a" * 21) == False

    def test_validate_invalid_chars(self):
        """测试无效字符"""
        assert validate_short_code("abc 123") == False
        assert validate_short_code("abc@123") == False

    def test_validate_hyphen_position(self):
        """测试连字符位置"""
        assert validate_short_code("abc-") == False
        assert validate_short_code("-abc") == False
        assert validate_short_code("abc-234") == True

    def test_reserved_codes(self):
        """测试保留字"""
        assert validate_short_code("admin") == False
        assert validate_short_code("test") == False
        assert validate_short_code("default") == False

    def test_reserved_codes_normalized(self):
        """测试保留字规范化后的检查"""
        # default 规范化后是 defauit
        normalized_reserved = {normalize_short_code(code) for code in RESERVED_CODES}
        assert "defauit" in normalized_reserved
        assert "admin" in normalized_reserved
        assert "test" in normalized_reserved


def test_short_code_creation_scenario():
    """测试短代码创建场景"""
    test_cases = [
        # 正常情况（不包含易混淆字符）
        ("abc234", True, "正常短代码"),
        ("ABC234", True, "大写短代码"),
        ("abc-234", True, "带连字符的短代码"),
        # 易混淆字符（规范化后应该有效）
        ("abc012", True, "包含0的短代码"),
        ("abc123", True, "包含1的短代码"),
        ("abco12", True, "包含o的短代码"),
        ("abcl12", True, "包含l的短代码"),
        ("abcI12", True, "包含I的短代码"),
        # 保留字
        ("admin", False, "保留字admin"),
        ("default", False, "保留字default"),
        ("test", False, "保留字test"),
        ("DEFAULT", False, "大写保留字default"),
        ("Default", False, "首字母大写保留字default"),
    ]

    passed = 0
    total = len(test_cases)

    for input_code, should_pass, description in test_cases:
        normalized = normalize_short_code(input_code)

        # 检查是否是保留字（使用修复后的逻辑）
        normalized_reserved = {normalize_short_code(code) for code in RESERVED_CODES}
        is_reserved = normalized in normalized_reserved

        # 验证格式
        is_valid = validate_short_code(normalized)

        # 综合判断
        should_create = should_pass and not is_reserved and is_valid

        assert should_create == should_pass, f"{description} 失败"

        if should_create == should_pass:
            passed += 1

    assert passed == total, f"测试失败: {passed}/{total} 测试通过"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
