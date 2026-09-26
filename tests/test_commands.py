"""命令解析测试：目标串解析与群号提取。"""

from __future__ import annotations

import pytest

from streaming_parser.commands import group_id_of, parse_target


class TestParseTarget:
    def test_plain_digits_is_room(self):
        assert parse_target("21452505") == ("room", 21452505)

    def test_digits_with_spaces(self):
        assert parse_target("  5440  ") == ("room", 5440)

    def test_live_url_is_room(self):
        assert parse_target("https://live.bilibili.com/21452505") == ("room", 21452505)

    def test_live_url_with_query_is_room(self):
        url = "https://live.bilibili.com/21452505?broadcast_type=0&from=search"
        assert parse_target(url) == ("room", 21452505)

    def test_space_url_is_uid(self):
        assert parse_target("https://space.bilibili.com/401742377") == ("uid", 401742377)

    def test_uid_prefix_is_uid(self):
        assert parse_target("uid:401742377") == ("uid", 401742377)

    @pytest.mark.parametrize("bad", ["", "   ", "不是数字", "https://example.com/abc"])
    def test_invalid_input_raises(self, bad):
        with pytest.raises(ValueError):
            parse_target(bad)

    def test_overlong_input_raises(self):
        with pytest.raises(ValueError):
            parse_target("1" * 300)


class TestGroupIdOf:
    def test_group_event_returns_id(self):
        assert group_id_of({"message_type": "group", "group_id": 123}) == 123

    def test_group_id_as_string(self):
        assert group_id_of({"message_type": "group", "group_id": "456"}) == 456

    def test_private_event_returns_zero(self):
        assert group_id_of({"message_type": "private", "user_id": 1}) == 0

    def test_missing_group_id_returns_zero(self):
        assert group_id_of({"message_type": "group"}) == 0

    def test_bad_group_id_returns_zero(self):
        assert group_id_of({"message_type": "group", "group_id": "abc"}) == 0

