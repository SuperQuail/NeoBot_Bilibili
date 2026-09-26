"""头像/封面等图片资源的下载与本地缓存。

渲染卡片需要主播头像与直播封面，都是 B 站 CDN 上的图片。这里做三件事：
1. 走本插件统一的请求头（Referer 指向直播间，避免被 CDN 拒绝）；
2. 落盘缓存，避免每次推送都重复下载、也避免平台抖动导致卡片缺图；
3. 转成 data URI 直接嵌进 HTML，渲染时不需要任何外部网络请求。
"""

from __future__ import annotations

import base64
import hashlib
import time
from pathlib import Path

from .bilibili.headers import DEFAULT_UA

#: 常见图片格式的魔数探测（够用即可，B 站头像/封面只有这几种）
_MAGIC: tuple[tuple[bytes, str], ...] = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"GIF8", "image/gif"),
    (b"RIFF", "image/webp"),
)


def sniff_mime(data: bytes) -> str:
    """按魔数判断图片类型；识别不了就按 jpeg 处理。"""
    for magic, mime in _MAGIC:
        if data.startswith(magic):
            return mime
    return "image/jpeg"


class AssetCache:
    """按 URL 哈希落盘的图片缓存，返回 data URI。"""

    def __init__(
        self,
        root: Path,
        *,
        timeout: float = 15.0,
        user_agent: str | None = None,
        ttl_days: int = 14,
        max_bytes: int = 8 * 1024 * 1024,
    ) -> None:
        self.root = Path(root)
        self.timeout = timeout
        self.user_agent = user_agent or DEFAULT_UA
        self.ttl_seconds = max(0, int(ttl_days)) * 86400
        self.max_bytes = max_bytes

    def path_for(self, url: str) -> Path:
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()
        return self.root / digest[:2] / digest

    def _read_cache(self, url: str) -> bytes | None:
        path = self.path_for(url)
        try:
            stat = path.stat()
        except OSError:
            return None
        if self.ttl_seconds and time.time() - stat.st_mtime > self.ttl_seconds:
            return None
        try:
            return path.read_bytes()
        except OSError:
            return None

    def _write_cache(self, url: str, data: bytes) -> None:
        path = self.path_for(url)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError:
            pass

    def purge_expired(self) -> int:
        """删除过期缓存文件，返回删除数量。"""
        if not self.ttl_seconds or not self.root.exists():
            return 0
        removed = 0
        cutoff = time.time() - self.ttl_seconds
        for item in self.root.rglob("*"):
            if not item.is_file():
                continue
            try:
                if item.stat().st_mtime < cutoff:
                    item.unlink()
                    removed += 1
            except OSError:
                continue
        return removed

    async def fetch_bytes(self, url: str) -> bytes | None:
        if not url:
            return None
        cached = self._read_cache(url)
        if cached is not None:
            return cached
        try:
            import httpx

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    url,
                    headers={
                        "user-agent": self.user_agent,
                        "referer": "https://live.bilibili.com/",
                        "accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
                    },
                )
        except Exception:
            return None
        if response.status_code != 200:
            return None
        data = response.content
        if not data or len(data) > self.max_bytes:
            return None
        self._write_cache(url, data)
        return data

    async def fetch_data_uri(self, url: str) -> str:
        """取图片并转成 data URI；失败返回空串（渲染端自行降级）。"""
        data = await self.fetch_bytes(url)
        if not data:
            return ""
        mime = sniff_mime(data)
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{mime};base64,{encoded}"

