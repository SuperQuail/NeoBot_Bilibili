"""数据层与轮询落库测试（需要真实的 neobot_modloader，CI 里会跳过）。"""

from __future__ import annotations

import pytest

modloader = pytest.importorskip('neobot_modloader')
if getattr(modloader, 'IS_TEST_STUB', False):
    pytest.skip('需要真实的 neobot_modloader（CI 环境没有 NeoBot 依赖）', allow_module_level=True)

# 这些导入必须在 importorskip 之后：没有真实 modloader 时整模块跳过，
# 否则收集阶段就会因为缺依赖而报错。因此这里显式豁免 E402。
from neobot_modloader import PluginDatabase  # noqa: E402
from streaming_parser import db as pdb  # noqa: E402
from streaming_parser.bilibili.models import LiveRoomInfo  # noqa: E402
from streaming_parser.poller import EVENT_LIVE, EVENT_LIVE_END, LivePoller  # noqa: E402


@pytest.fixture
async def database(tmp_path):
    database = PluginDatabase(
        'streaming_parser',
        pdb.DATABASE_NAME,
        filename=pdb.DATABASE_FILENAME,
        metadata=pdb.Base.metadata,
        migrations=pdb.MIGRATIONS,
    )
    await database.bind(tmp_path)
    try:
        yield database
    finally:
        await database.close()


class TestSubscriptions:
    async def test_upsert_creates_then_updates(self, database):
        async with database.transaction() as session:
            row, created = await pdb.upsert_subscription(
                session, group_id=100, room_id=5440, uid=9, name='甲'
            )
            assert created is True
            assert row.name == '甲'
        async with database.transaction() as session:
            row, created = await pdb.upsert_subscription(
                session, group_id=100, room_id=5440, uid=9, name='乙'
            )
            assert created is False
            assert row.name == '乙'
        async with database.session() as session:
            rows = await pdb.list_group_subscriptions(session, 100)
        assert len(rows) == 1

    async def test_push_flags_default_and_toggle(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(
                session, group_id=1, room_id=1, push_live=True, push_live_end=False
            )
        async with database.transaction() as session:
            row = pdb.sub_view(
                await pdb.set_subscription_flags(
                    session, 1, 1, push_live=False, push_live_end=True
                )
            )
        assert row is not None
        assert row.push_live is False
        assert row.push_live_end is True

    async def test_set_flags_on_unknown_room_returns_none(self, database):
        async with database.transaction() as session:
            assert await pdb.set_subscription_flags(session, 1, 999) is None

    async def test_remove_subscription(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=1, room_id=7)
        async with database.transaction() as session:
            assert await pdb.remove_subscription(session, 1, 7) is True
        async with database.transaction() as session:
            assert await pdb.remove_subscription(session, 1, 7) is False

    async def test_distinct_rooms_dedupe_across_groups(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=1, room_id=10)
            await pdb.upsert_subscription(session, group_id=2, room_id=10)
            await pdb.upsert_subscription(session, group_id=2, room_id=20)
        async with database.session() as session:
            assert await pdb.distinct_room_ids(session) == [10, 20]

    async def test_followers_of_room(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=1, room_id=10)
            await pdb.upsert_subscription(session, group_id=2, room_id=10)
            await pdb.upsert_subscription(session, group_id=3, room_id=30)
        async with database.session() as session:
            followers = await pdb.followers_of_room(session, 10)
        assert sorted(row.group_id for row in followers) == [1, 2]


class TestGroupSettings:
    async def test_ensure_creates_with_defaults(self, database):
        async with database.transaction() as session:
            setting = pdb.setting_view(
                await pdb.ensure_group_setting(
                    session, 5, {'ai_reply_live': False, 'card_style': 'neon'}
                )
            )
        assert setting is not None
        assert setting.group_id == 5
        assert setting.ai_reply_live is False
        assert setting.card_style == 'neon'
        assert setting.default_push_live is True

    async def test_ensure_is_idempotent(self, database):
        async with database.transaction() as session:
            first = pdb.setting_view(
                await pdb.ensure_group_setting(session, 5, {'card_style': 'neon'})
            )
        async with database.transaction() as session:
            second = pdb.setting_view(
                await pdb.ensure_group_setting(session, 5, {'card_style': 'sakura'})
            )
        assert second is not None and first is not None
        assert second.card_style == 'neon'
        assert first.group_id == second.group_id

    async def test_get_missing_returns_none(self, database):
        async with database.session() as session:
            assert await pdb.get_group_setting(session, 404) is None


class TestRoomState:
    async def test_upsert_creates_then_updates(self, database):
        async with database.transaction() as session:
            row = await pdb.upsert_room_state(session, 10, live_status=0, title='旧')
            assert row.live_status == 0
        async with database.transaction() as session:
            row = await pdb.upsert_room_state(session, 10, live_status=1, title='新')
            assert row.live_status == 1
            assert row.title == '新'
        async with database.session() as session:
            stored = await pdb.get_room_state(session, 10)
        assert stored is not None and stored.live_status == 1

    async def test_missing_state_returns_none(self, database):
        async with database.session() as session:
            assert await pdb.get_room_state(session, 999) is None


class FakeClient:
    def __init__(self, script):
        self.script = script

    async def fetch_live_room_info(self, room_id):
        status = self.script[room_id].pop(0)
        return LiveRoomInfo(
            room_id=room_id,
            short_id=0,
            uid=1,
            title='t',
            live_status=status,
            live_time=None,
            online=5,
        )


class TestPollOnce:
    async def test_transitions_across_polls(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=1, room_id=10)
        client = FakeClient({10: [0, 1, 1, 0]})
        poller = LivePoller(client=client, database=database, poll_interval=15)

        first, stats_first = await poller.poll_once()
        assert first == []
        assert stats_first.checked == 1

        second, _ = await poller.poll_once()
        assert [item.kind for item in second] == [EVENT_LIVE]
        assert second[0].room_id == 10
        assert second[0].previous_status == 0

        third, _ = await poller.poll_once()
        assert third == []

        fourth, _ = await poller.poll_once()
        assert [item.kind for item in fourth] == [EVENT_LIVE_END]
        assert fourth[0].previous_status == 1

    async def test_api_failure_is_counted_not_raised(self, database):
        async with database.transaction() as session:
            await pdb.upsert_subscription(session, group_id=1, room_id=10)

        class Boom:
            async def fetch_live_room_info(self, room_id):
                raise RuntimeError('network down')

        poller = LivePoller(client=Boom(), database=database, poll_interval=15)
        transitions, stats = await poller.poll_once()
        assert transitions == []
        assert stats.failed == 1
        assert stats.checked == 0

    async def test_no_subscriptions_is_noop(self, database):
        poller = LivePoller(client=FakeClient({}), database=database, poll_interval=15)
        transitions, stats = await poller.poll_once()
        assert transitions == []
        assert stats.checked == 0

