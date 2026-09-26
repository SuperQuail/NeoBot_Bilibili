"""NeoBot B 站解析插件（空壳骨架）。

当前版本只提供可被 neobot_modloader 直接识别的插件骨架与生命周期钩子；
协议实现按 `docs/roadmap.md` 的优先级逐步落地：

- P0 直播间解析（HTTP 元信息、短号/房间号互转、开播轮询）
- P1 WBI 签名与视频/评论/动态接口
- P2 直播间弹幕长连接（参考项目未实现，需另行调研协议）

约束：实现尽可能使用 Python；涉及前端的部分必须预编译入库，部署侧不依赖
Node/前端工具链，详见 `docs/frontend.md`。
"""

from __future__ import annotations

from pydantic import BaseModel

from neobot_modloader import Plugin


class BilibiliConfig(BaseModel):
    """插件配置模型，字段与 plugin.toml 的 [config] 一一对应。"""

    request_timeout: float = 10.0
    cookie: str = ""
    user_agent: str = ""


plugin = Plugin(
    "bilibili",
    version="0.1.0",
    description="B 站数据解析：直播间、用户与投稿信息（amagi 协议的纯 Python 实现）",
    author="SuperQuail",
    config=BilibiliConfig,
)


@plugin.on_load
async def _on_load(ctx) -> None:
    ctx.logger.info("%s 已加载（空壳骨架，协议实现待落地）", ctx.plugin_name)


@plugin.on_startup
async def _on_startup(ctx) -> None:
    ctx.logger.info("%s 已启动", ctx.plugin_name)


@plugin.on_shutdown
async def _on_shutdown(ctx) -> None:
    ctx.logger.info("%s 已停止", ctx.plugin_name)
