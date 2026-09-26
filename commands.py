"""订阅类命令：监听 / 取消监听 / 监听列表 / 开播下播推送开关。

命令用 MessagePattern 的 <name:type> 语法；群号从 reply.event 里取，
所以这些命令天然只能在群里用。设置类命令见 settings_commands.py。
"""

from __future__ import annotations

import re
from typing import Any

from . import db
from .bilibili.errors import BilibiliAPIError, BilibiliTransportError
from .bilibili.urls import live_room_page_url

MAX_TARGET_LENGTH = 256
UNNAMED = "未命名"

_DIGITS = re.compile("[0-9]+")


def parse_target(raw: str) -> tuple[str, int]:
    """把用户输入解析成 (kind, id)，kind 为 room 或 uid。

    支持：纯数字（房间号或短号）、直播间链接、UP 主空间链接、uid 前缀写法。
    """
    text = (raw or "").strip()
    if not text or len(text) > MAX_TARGET_LENGTH:
        raise ValueError("目标不能为空")
    lowered = text.lower()
    if "space.bilibili.com" in lowered or lowered.startswith("uid"):
        match = _DIGITS.search(text)
        if match is None:
            raise ValueError("没有从输入里找到 UID")
        return "uid", int(match.group(0))
    if "live.bilibili.com" in lowered:
        match = _DIGITS.search(text)
        if match is None:
            raise ValueError("没有从链接里找到房间号")
        return "room", int(match.group(0))
    if text.isdigit():
        return "room", int(text)
    raise ValueError("请提供房间号、短号、直播间链接或 UP 主空间链接")


def group_id_of(event: dict[str, Any]) -> int:
    """取群号；私聊或拿不到时返回 0。"""
    if str(event.get("message_type") or "") != "group":
        return 0
    value = event.get("group_id")
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def register(plugin: Any, state: Any) -> None:
    """挂订阅类命令；末尾转交给设置类命令。"""

    @plugin.command("监听 <target:str>")
    async def _subscribe(target: str, reply: Any, config: Any) -> None:
        group_id = group_id_of(reply.event)
        if not group_id:
            await reply.send("这个命令只能在群里用。")
            return
        try:
            kind, value = parse_target(target)
        except ValueError as exc:
            await reply.send("参数不对：" + str(exc))
            return
        try:
            resolved = await state.resolve_target(kind, value)
        except (BilibiliAPIError, BilibiliTransportError) as exc:
            await reply.send("查询直播间失败：" + str(exc))
            return
        except ValueError as exc:
            await reply.send(str(exc))
            return
        async with state.database.transaction() as session:
            _, created = await db.upsert_subscription(
                session,
                group_id=group_id,
                room_id=resolved["room_id"],
                short_id=resolved.get("short_id", 0),
                uid=resolved.get("uid", 0),
                name=resolved.get("name", ""),
                avatar_url=resolved.get("avatar_url", ""),
                push_live=config.default_push_live,
                push_live_end=config.default_push_live_end,
            )
        head = "已开始监听" if created else "更新了监听信息"
        name = resolved.get("name") or UNNAMED
        await reply.send(
            head + "：" + name + "\n"
            + "房间：" + live_room_page_url(resolved["room_id"]) + "\n"
            + "用 /开播状态 可以看到本群关注的全部主播。"
        )

    @plugin.command("取消监听 <target:str>")
    async def _unsubscribe(target: str, reply: Any) -> None:
        group_id = group_id_of(reply.event)
        if not group_id:
            await reply.send("这个命令只能在群里用。")
            return
        try:
            kind, value = parse_target(target)
        except ValueError as exc:
            await reply.send("参数不对：" + str(exc))
            return
        row = await state.find_subscription(group_id, kind, value)
        if row is None:
            await reply.send("本群没有监听这个直播间。")
            return
        async with state.database.transaction() as session:
            removed = await db.remove_subscription(session, group_id, row.room_id)
        if removed:
            await reply.send("已取消监听：" + (row.name or UNNAMED))
        else:
            await reply.send("取消失败，请稍后再试。")

    @plugin.command("监听列表")
    async def _list(reply: Any) -> None:
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
        lines = ["本群共监听 " + str(len(rows)) + " 个直播间："]
        for index, row in enumerate(rows, start=1):
            flags = ["开播推送" + ("开" if row.push_live else "关")]
            flags.append("下播推送" + ("开" if row.push_live_end else "关"))
            lines.append(
                str(index) + ". " + (row.name or UNNAMED)
                + "（房间 " + str(row.room_id) + "） · " + "、".join(flags)
            )
        lines.append("开关：/开播推送 房间号 开|关，/下播推送 房间号 开|关")
        await reply.send("\n".join(lines))

    @plugin.command("开播推送 <target:str> <value:bool>")
    async def _toggle_live(target: str, value: bool, reply: Any) -> None:
        await _toggle(reply, target, value, kind="live", state=state)

    @plugin.command("下播推送 <target:str> <value:bool>")
    async def _toggle_live_end(target: str, value: bool, reply: Any) -> None:
        await _toggle(reply, target, value, kind="live_end", state=state)

    from .settings_commands import register_settings

    register_settings(plugin, state)


async def _toggle(
    reply: Any, target: str, value: bool, *, kind: str, state: Any
) -> None:
    """切换某个直播间的开播/下播推送开关。"""
    group_id = group_id_of(reply.event)
    if not group_id:
        await reply.send("这个命令只能在群里用。")
        return
    try:
        target_kind, number = parse_target(target)
    except ValueError as exc:
        await reply.send("参数不对：" + str(exc))
        return
    row = await state.find_subscription(group_id, target_kind, number)
    if row is None:
        await reply.send("本群没有监听这个直播间，先用 /监听 添加。")
        return
    async with state.database.transaction() as session:
        await db.set_subscription_flags(
            session,
            group_id,
            row.room_id,
            push_live=value if kind == "live" else None,
            push_live_end=value if kind == "live_end" else None,
        )
    label = "开播" if kind == "live" else "下播"
    state_text = "开启" if value else "关闭"
    await reply.send("已" + state_text + " " + (row.name or UNNAMED) + " 的" + label + "推送。")


__all__ = ["MAX_TARGET_LENGTH", "UNNAMED", "group_id_of", "parse_target", "register"]
