"""萤石开放平台(open.ys7.com) API 客户端。

用于查询设备告警消息，作为「移动侦测触发本地录像」的数据源。

与主 ``EzvizClient``(萤石账号 + sessionId)是两套独立凭证体系：
本模块用开放平台应用的 AppKey/AppSecret 换 accessToken(官方 7 天有效)。
设备需先绑定到开放平台应用下(用设备序列号 + 验证码)，否则查不到告警。
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

from .pyezvizapi.exceptions import PyEzvizError

_LOGGER = logging.getLogger(__name__)

# 中国区开放平台网关
OPEN_PLATFORM_URL = "https://open.ys7.com"
API_TOKEN_GET = "/api/lapp/token/get"
API_ALARM_LIST = "/api/lapp/alarm/device/list"

# accessToken 官方 7 天有效，提前 1 小时刷新，避免临界过期
_TOKEN_REFRESH_AHEAD_SECONDS = 3600
# 告警时间戳为毫秒，这里统一用毫秒
_MS_PER_DAY = 24 * 3600 * 1000


class EzvizOpenPlatformClient:
    """萤石开放平台客户端，内置 accessToken 缓存。"""

    def __init__(self, app_key: str, app_secret: str, timeout: int = 25) -> None:
        """初始化开放平台客户端。

        Args:
            app_key: 开放平台应用 AppKey(32 位十六进制)。
            app_secret: 开放平台应用 AppSecret(32 位十六进制)。
            timeout: 单次请求超时秒数。
        """
        self._app_key = app_key
        self._app_secret = app_secret
        self._timeout = timeout
        self._session = requests.session()
        self._access_token: str | None = None
        self._token_expire: float = 0.0

    def _post(self, endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
        """POST 到开放平台并校验业务码，返回完整 JSON。"""
        try:
            resp = self._session.post(
                f"{OPEN_PLATFORM_URL}{endpoint}",
                data=data,
                timeout=self._timeout,
            )
            resp.raise_for_status()
        except requests.HTTPError as err:
            raise PyEzvizError(f"开放平台请求失败 {endpoint}: {err}") from err
        except requests.RequestException as err:
            raise PyEzvizError(f"开放平台网络异常 {endpoint}: {err}") from err

        try:
            result = resp.json()
        except ValueError as err:
            raise PyEzvizError(f"开放平台返回非 JSON {endpoint}: {resp.text[:200]}") from err

        if str(result.get("code")) != "200":
            raise PyEzvizError(f"开放平台业务失败 {endpoint}: {result}")
        return result

    def get_access_token(self) -> str:
        """获取(或复用缓存的)accessToken。"""
        if self._access_token and time.time() < self._token_expire:
            return self._access_token

        result = self._post(
            API_TOKEN_GET,
            {"appKey": self._app_key, "appSecret": self._app_secret},
        )
        data = result.get("data") or {}
        token = data.get("accessToken")
        if not token:
            raise PyEzvizError(f"开放平台未返回 accessToken: {result}")

        self._access_token = token
        expire_ms = data.get("expireTime")
        if expire_ms:
            self._token_expire = expire_ms / 1000 - _TOKEN_REFRESH_AHEAD_SECONDS
        else:
            self._token_expire = time.time() + 6 * 24 * 3600
        return token

    def get_alarm_list(
        self,
        serial: str,
        start_time: int,
        end_time: int,
        *,
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        """查询设备在 [start_time, end_time] 内的告警消息(毫秒时间戳)。

        返回按 alarmTime 升序排列的告警列表，每条含 alarmId/alarmType/alarmTime/
        channelNo/alarmPicUrl 等字段。
        """
        result = self._post(
            API_ALARM_LIST,
            {
                "accessToken": self.get_access_token(),
                "deviceSerial": serial,
                "startTime": start_time,
                "endTime": end_time,
                "pageStart": 0,
                "pageSize": page_size,
            },
        )
        data = result.get("data")
        return data if isinstance(data, list) else []
