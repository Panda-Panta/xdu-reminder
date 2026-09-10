# Copyright 2026 XDU Reminder Service
# 网络客户端模块 — httpx 封装 + Cookie 持久化
#
# 移植自 traintime_pda: network_client.dart

import json
import pickle
from pathlib import Path
from typing import Optional

import httpx
from loguru import logger

# 默认 User-Agent (与原始 Dart 应用保持一致)
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36 XDYou/2.0.0"
)

# eHall 专用请求头
EHALL_HEADERS = {
    "Referer": "http://ehall.xidian.edu.cn/new/index_xd.html",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/webp,image/apng,*/*;q=0.8,"
        "application/signed-exchange;v=b3;q=0.9"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6",
    "Accept-Encoding": "identity",
    "Connection": "Keep-Alive",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}


class CookieStore:
    """Cookie 持久化管理

    使用 pickle 序列化 httpx.Cookies 到文件。
    """

    def __init__(self, data_dir: str | Path, name: str = "ids"):
        self._dir = Path(data_dir) / "cookies"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._path = self._dir / f"{name}.pkl"

    def load(self) -> httpx.Cookies:
        """从文件加载 Cookies"""
        cookies = httpx.Cookies()
        if self._path.exists():
            try:
                with open(self._path, "rb") as f:
                    saved = pickle.load(f)
                if isinstance(saved, list):
                    for item in saved:
                        cookies.set(
                            item["name"],
                            item["value"],
                            domain=item.get("domain", ""),
                            path=item.get("path", "/"),
                        )
                elif isinstance(saved, dict):
                    for name, value in saved.items():
                        cookies.set(name, value)
                elif isinstance(saved, httpx.Cookies):
                    cookies = saved
                logger.debug("已加载 Cookie")
            except Exception as e:
                logger.warning("Cookie 加载失败: {}", e)
        return cookies

    def save(self, cookies: httpx.Cookies) -> None:
        """保存 Cookies 到文件"""
        try:
            cookie_list = []
            jar = getattr(cookies, "jar", cookies)
            for c in jar:
                cookie_list.append({
                    "name": c.name,
                    "value": c.value,
                    "domain": getattr(c, "domain", ""),
                    "path": getattr(c, "path", "/"),
                })
            with open(self._path, "wb") as f:
                pickle.dump(cookie_list, f)
            logger.debug("已保存 Cookie: {} 个", len(cookie_list))
        except Exception as e:
            logger.warning("Cookie 保存失败: {}", e)

    def clear(self) -> None:
        """清除持久化 Cookie"""
        if self._path.exists():
            self._path.unlink()
            logger.info("已清除 Cookie 文件: {}", self._path)


class NetworkClient:
    """共享网络客户端管理器

    提供 IDS 和 eHall 两种预配置的 httpx.Client。
    """

    def __init__(self, data_dir: str | Path):
        self.data_dir = Path(data_dir)
        self._ids_cookie_store = CookieStore(data_dir, "ids")
        self._ids_cookies = self._ids_cookie_store.load()
        self._ids_client: Optional[httpx.Client] = None

    @property
    def ids_client(self) -> httpx.Client:
        """IDS 统一认证客户端 (禁止自动重定向)"""
        if self._ids_client is None or self._ids_client.is_closed:
            self._ids_client = httpx.Client(
                cookies=self._ids_cookies,
                headers={"User-Agent": DEFAULT_USER_AGENT},
                follow_redirects=False,
                timeout=httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0),
            )
        return self._ids_client

    def save_cookies(self) -> None:
        """持久化当前 Cookie"""
        if self._ids_client:
            self._ids_cookie_store.save(self._ids_client.cookies)

    def clear_cookies(self) -> None:
        """清除所有 Cookie"""
        self._ids_cookie_store.clear()
        if self._ids_client:
            self._ids_client.cookies.clear()

    def get_cookie_string(self, domain: str = "ids.xidian.edu.cn") -> str:
        """获取指定域名的 Cookie 字符串"""
        return cookies_to_string(self.ids_client.cookies, domain=domain)

    def close(self) -> None:
        """关闭所有客户端连接"""
        self.save_cookies()
        if self._ids_client and not self._ids_client.is_closed:
            self._ids_client.close()
            logger.info("网络客户端已关闭")


def is_in_school() -> bool:
    """检查是否在校园网内

    通过访问 notice.xidian.edu.cn 判断。
    """
    try:
        resp = httpx.get(
            "https://notice.xidian.edu.cn",
            follow_redirects=True,
            timeout=5.0,
        )
        return "校外访问" not in resp.text
    except Exception as e:
        logger.warning("校园网检测失败，默认视为校外: {}", e)
        return False


_client_instances: dict[str, NetworkClient] = {}


def get_network_client(data_dir: str | Path) -> NetworkClient:
    """获取或创建指定 data_dir 的 NetworkClient 单例"""
    key = str(Path(data_dir).resolve())
    if key not in _client_instances:
        _client_instances[key] = NetworkClient(data_dir)
    return _client_instances[key]


def get_ids_client(data_dir: str | Path) -> httpx.Client:
    """获取 IDS HTTP 客户端"""
    return get_network_client(data_dir).ids_client


def cookies_to_string(cookies: httpx.Cookies, domain: str = "") -> str:
    """安全地将 Cookies 转换为 'name=value; ...' 字符串，避免同名 Cookie 导致的 CookieConflict"""
    jar = getattr(cookies, "jar", cookies)
    parts = []
    seen = set()
    for c in jar:
        c_domain = getattr(c, "domain", "")
        if not domain or not c_domain or domain in c_domain or c_domain in domain:
            key = (c.name, c.value)
            if key not in seen:
                seen.add(key)
                parts.append(f"{c.name}={c.value}")
    return "; ".join(parts)


def save_cookies(client: httpx.Client, data_dir: str | Path) -> None:
    """持久化指定客户端的 Cookie"""
    store = CookieStore(data_dir, "ids")
    store.save(client.cookies)


def load_cookies(client: httpx.Client, data_dir: str | Path) -> None:
    """加载持久化 Cookie 到客户端，按 domain 和 path 还原，避免 CookieConflict"""
    store = CookieStore(data_dir, "ids")
    cookies = store.load()
    jar = getattr(cookies, "jar", cookies)
    for c in jar:
        try:
            if hasattr(c, "name") and hasattr(c, "value"):
                client.cookies.set(
                    c.name,
                    c.value,
                    domain=getattr(c, "domain", ""),
                    path=getattr(c, "path", "/"),
                )
            elif isinstance(c, dict):
                client.cookies.set(
                    c.get("name"),
                    c.get("value"),
                    domain=c.get("domain", ""),
                    path=c.get("path", "/"),
                )
        except Exception as e:
            logger.debug("跳过异常 Cookie: {}", e)

