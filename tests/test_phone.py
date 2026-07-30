"""Tests for phone number utilities (phone.py)."""
import sys
from pathlib import Path

# Project root for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from phone import normalize_phone_number, is_urdu, text_dir_attrs


# ---------------------------------------------------------------------------
# normalize_phone_number
# ---------------------------------------------------------------------------

class TestNormalizePhoneNumber:
    def test_pakistani_local_valid(self):
        """03XX format → +92XX"""
        assert normalize_phone_number("03001234567") == "+923001234567"
        assert normalize_phone_number("03151234567") == "+923151234567"

    def test_pakistani_local_with_dashes(self):
        """Dashes and spaces should be stripped."""
        assert normalize_phone_number("0300-1234567") == "+923001234567"
        assert normalize_phone_number("0300 1234567") == "+923001234567"

    def test_e164_already(self):
        """Already E.164 numbers pass through."""
        assert normalize_phone_number("+923001234567") == "+923001234567"
        assert normalize_phone_number("+12025551234") == "+12025551234"

    def test_e164_edge_length(self):
        """Minimum and maximum E.164 length."""
        assert normalize_phone_number("+123456789") == "+123456789"      # 10 digits
        assert normalize_phone_number("+123456789012345") == "+123456789012345"  # 16 digits

    def test_92_prefix_no_plus(self):
        """'92XXXXXXXXXX' (12 digits) → +92XXXXXXXXXX"""
        assert normalize_phone_number("923001234567") == "+923001234567"

    def test_invalid_number(self):
        """Too short, missing digits, or non-numeric → None."""
        assert normalize_phone_number("") is None
        assert normalize_phone_number("abc") is None
        assert normalize_phone_number("123") is None
        assert normalize_phone_number("+92") is None          # truncated
        assert normalize_phone_number("0300123456") is None    # 10 digits (local expects 11)
        # Note: 11-digit local starting with 03 is valid; 10-digit is invalid

    def test_none_input(self):
        """None input → None."""
        assert normalize_phone_number(None) is None

    def test_whitespace_only(self):
        """Only whitespace → None after stripping."""
        assert normalize_phone_number("   ") is None

    def test_international_not_pakistani(self):
        """Non-PK international numbers should pass through if E.164."""
        assert normalize_phone_number("+447911123456") == "+447911123456"

    def test_numeric_string_with_extra_chars(self):
        """Parentheses around area codes should be stripped."""
        assert normalize_phone_number("+1 (202) 555-0123") == "+12025550123"


# ---------------------------------------------------------------------------
# is_urdu
# ---------------------------------------------------------------------------

class TestIsUrdu:
    def test_urdu_text(self):
        """Strings containing Urdu script characters → True."""
        assert is_urdu("السلام علیکم") is True
        assert is_urdu("یہ ایک ٹیسٹ ہے۔") is True

    def test_english_text(self):
        """Strings with only Latin characters → False."""
        assert is_urdu("Hello World") is False
        assert is_urdu("Test 123") is False

    def test_mixed_text(self):
        """Mixed text with Urdu characters → True."""
        assert is_urdu("میرا name Waseem ہے") is True

    def test_empty_string(self):
        """Empty string → False."""
        assert is_urdu("") is False

    def test_none_input(self):
        """None input → False."""
        assert is_urdu(None) is False


# ---------------------------------------------------------------------------
# text_dir_attrs
# ---------------------------------------------------------------------------

class TestTextDirAttrs:
    def test_urdu_text_returns_rtl(self):
        """Urdu text → rtl attrs with urdu class."""
        attrs = text_dir_attrs("السلام علیکم")
        assert 'dir="rtl"' in attrs
        assert 'lang="ur"' in attrs
        assert "urdu-text" in attrs

    def test_english_text_returns_ltr(self):
        """English text → ltr dir."""
        attrs = text_dir_attrs("Hello World")
        assert 'dir="ltr"' in attrs
        assert "urdu-text" not in attrs

    def test_none_input(self):
        """None → ltr dir."""
        attrs = text_dir_attrs(None)
        assert 'dir="ltr"' in attrs

    def test_empty_string(self):
        """Empty string → ltr dir."""
        attrs = text_dir_attrs("")
        assert 'dir="ltr"' in attrs
