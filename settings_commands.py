"""设置类命令：开播状态总览图 / 卡片风格 / config。"""

from __future__ import annotations

import asyncio
from typing import Any

from . import db
from .commands import UNNAMED, group_id_of
from .render import STYLE_ORDER

OVERVIEW_TIMEOUT = 25.0
OVERVIEW_FILENAME = "streaming_parser_overview.png"
RANDOM_WORDS = ("随机", "random")


def _style_list_text() -> str:
    return " / ".join(STYLE_ORDER)


def _match_style(value: str | None) -> str | None:
    """把用户输入的风格名归一成已登记风格或 random；不合法返回 None。"""
    wanted = (value or "").strip().lower()
    if not wanted:
        return None
    if wanted in RANDOM_WORDS:
        return "random"
    if wanted in STYLE_ORDER:
        return wanted
    return None


def _parse_switch(value: str | None) -> bool | None:
    text = (value or "").strip().lower()
    if text in {"1", "true", "yes", "y", "on", "开", "开启"}:
        return True
    if text in {"0", "false", "no", "n", "off", "关", "关闭"}:
        return False
    return None


def config_text(setting: Any, config: Any) -> str:
    """/config 无参数时的说明 + 当前值。"""
    default_style = getattr(config, "default_card_style", "random") if config else "random"
    return "\n".join([
        "本群推送设置：",
        "  开播AI：" + ("开" if setting.ai_reply_live else "关"),
        "  下播AI：" + ("开" if setting.ai_reply_live_end else "关"),
        "  卡片风格：" + (setting.card_style or default_style),
        "  新订阅默认开播推送：" + ("开" if setting.default_push_live else "关"),
        "  新订阅默认下播推送：" + ("开" if setting.default_push_live_end else "关"),
        "",
        "改法：",
        "  /config 开播AI 开|关    —— 开播推送后是否触发一次 AI 回复",
        "  /config 下播AI 开|关    —— 下播推送后是否触发一次 AI 回复",
        "  /config 风格 sakura|neon|minimal|随机",
        "  /config 开播推送默认 开|关",
        "  /config 下播推送默认 开|关",
        "只要卡片不要 AI 回复：/config 开播AI 关",
    ])


def register_settings(plugin: Any, state: Any) -> None:

    @plugin.command("开播状态")
    async def _overview(reply: Any, config: Any) -> None:
        group_id = group_id_of(reply.event)
        if not group_id:
            await reply.send("这个命令只能在群里用。")
            return
        async with state.database.session() as session:
            rows = [
                db.sub_view(row)
                for row in await db.list_group_subscriptions(session, group_id)
            ]
        if not rows:
            await reply.send("本群还没有监听任何直播间，用 /监听 房间号 添加。")
            return
        rows = rows[: int(config.overview_max_hosts)]
        async with state.database.session() as session:
            states = {}
            for row in rows:
                states[row.room_id] = db.room_view(
                    await db.get_room_state(session, row.room_id)
                )
        live_rows = [
            row for row in rows
            if states.get(row.room_id) is not None and int(states[row.room_id].live_status) == 1
        ]
        hosts = await state.build_overview_hosts(rows, states)
        title = "本群关注的主播"
        summary = (
            "共 " + str(len(rows)) + " 位，" + str(len(live_rows)) + " 位正在直播"
        )
        style = await state.style_for(group_id)
        image = None
        try:
            image = await asyncio.wait_for(
                state.renderer.render_overview(
                    hosts, style=style, title_text=title, summary_text=summary
                ),
                timeout=OVERVIEW_TIMEOUT,
            )
        except TimeoutError:
            image = None
        if image is not None:
            try:
                await reply.image(data=image, filename=OVERVIEW_FILENAME)
                return
            except Exception:
                pass
        lines = [title, summary, ""]
        for row in rows:
            state_row = states.get(row.room_id)
            mark = "开播中" if state_row is not None and int(state_row.live_status) == 1 else "未开播"
            room_title = state_row.title if state_row is not None and state_row.title else ""
            suffix = " · " + room_title if room_title else ""
            lines.append("[" + mark + "] " + (row.name or UNNAMED) + suffix)
        lines.append("")
        lines.append("（浏览器截图不可用，已退化成文字）")
        await reply.send("\n".join(lines))

    @plugin.command("卡片风格 [style:str]")
    async def _style(style: str | None, reply: Any) -> None:
        group_id = group_id_of(reply.event)
        if not group_id:
            await reply.send("这个命令只能在群里用。")
            return
        chosen = _match_style(style)
        if chosen is None:
            if style is None or not str(style).strip():
                current = await state.style_name_for(group_id)
                await reply.send("当前卡片风格：" + current + "\n可选：" + _style_list_text() + " 或 随机")
                return
            await reply.send("没有这个风格：" + str(style) + "\n可选：" + _style_list_text() + " 或 随机")
            return
        async with state.database.transaction() as session:
            setting = await db.ensure_group_setting(session, group_id)
            setting.card_style = chosen
        await reply.send("卡片风格已设为：" + ("每次随机" if chosen == "random" else chosen))

    @plugin.command("config [key:str] [value:str]")
    async def _config(key: str | None, value: str | None, reply: Any, config: Any) -> None:
        group_id = group_id_of(reply.event)
        if not group_id:
            await reply.send("这个命令只能在群里用。")
            return
        async with state.database.session() as session:
            setting = db.setting_view(await db.get_group_setting(session, group_id))
        if setting is None:
            async with state.database.transaction() as session:
                setting = db.setting_view(await db.ensure_group_setting(
                    session,
                    group_id,
                    {
                        "card_style": config.default_card_style,
                        "ai_reply_live": config.default_ai_reply_live,
                        "ai_reply_live_end": config.default_ai_reply_live_end,
                        "default_push_live": config.default_push_live,
                        "default_push_live_end": config.default_push_live_end,
                    },
                ))
        if key is None or not str(key).strip():
            await reply.send(config_text(setting, config))
            return
        await _apply(reply, state, group_id, str(key).strip(), value)


async def _apply(reply: Any, state: Any, group_id: int, key: str, value: str | None) -> None:
    """写入一项群配置。"""
    normalized = key.lower()
    if normalized in {"开播ai", "liveai", "ai开播"}:
        switch = _parse_switch(value)
        if switch is None:
            await reply.send("用法：/config 开播AI 开|关")
            return
        await _set_bool(state, group_id, "ai_reply_live", switch)
        await reply.send("开播后触发 AI 回复：" + ("已开启" if switch else "已关闭"))
        return
    if normalized in {"下播ai", "liveendai", "ai下播"}:
        switch = _parse_switch(value)
        if switch is None:
            await reply.send("用法：/config 下播AI 开|关")
            return
        await _set_bool(state, group_id, "ai_reply_live_end", switch)
        await reply.send("下播后触发 AI 回复：" + ("已开启" if switch else "已关闭"))
        return
    if normalized in {"风格", "style", "卡片风格"}:
        chosen = _match_style(value)
        if chosen is None:
            await reply.send("用法：/config 风格 " + _style_list_text() + "|随机")
            return
        async with state.database.transaction() as session:
            setting = await db.ensure_group_setting(session, group_id)
            setting.card_style = chosen
        await reply.send("卡片风格已设为：" + ("每次随机" if chosen == "random" else chosen))
        return
    if normalized in {"开播推送默认", "defaultpushlive"}:
        switch = _parse_switch(value)
        if switch is None:
            await reply.send("用法：/config 开播推送默认 开|关")
            return
        await _set_bool(state, group_id, "default_push_live", switch)
        await reply.send("新订阅默认开播推送：" + ("开" if switch else "关"))
        return
    if normalized in {"下播推送默认", "defaultpushliveend"}:
        switch = _parse_switch(value)
        if switch is None:
            await reply.send("用法：/config 下播推送默认 开|关")
            return
        await _set_bool(state, group_id, "default_push_live_end", switch)
        await reply.send("新订阅默认下播推送：" + ("开" if switch else "关"))
        return
    await reply.send("不认识的配置项：" + key + "\n\n" + config_text(await _setting(state, group_id), None))


async def _set_bool(state: Any, group_id: int, field: str, value: bool) -> None:
    async with state.database.transaction() as session:
        setting = await db.ensure_group_setting(session, group_id)
        setattr(setting, field, value)


async def _setting(state: Any, group_id: int) -> Any:
    async with state.database.transaction() as session:
        return db.setting_view(await db.ensure_group_setting(session, group_id))


__all__ = ["config_text", "register_settings"]
