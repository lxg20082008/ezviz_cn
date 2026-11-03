"""Provides the ezviz DataUpdateCoordinator."""

import asyncio
from datetime import timedelta
import logging
import time

from pyezvizapi.client import EzvizClient
from pyezvizapi.exceptions import (
    EzvizAuthTokenExpired,
    EzvizAuthVerificationCode,
    HTTPError,
    InvalidURL,
    PyEzvizError,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_URL, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    ALARM_POLL_INTERVAL,
    CONF_RFSESSION_ID,
    CONF_SESSION_ID,
    DOMAIN,
    EVENT_ALARM,
)
from .open_platform import EzvizOpenPlatformClient

_LOGGER = logging.getLogger(__name__)

type EzvizConfigEntry = ConfigEntry[EzvizDataUpdateCoordinator]


class EzvizDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching EZVIZ data."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: EzvizConfigEntry,
        *,
        api: EzvizClient,
        api_timeout: int,
    ) -> None:
        """Initialize global EZVIZ data updater."""
        self.ezviz_client = api
        self._api_timeout = api_timeout
        self._open_platform: EzvizOpenPlatformClient | None = None
        self._alarm_poll_task: asyncio.Task | None = None
        self._alarm_cursor_ms = 0  # 上次告警查询的结束时间戳(毫秒)
        self._alarm_device_id: str | None = None  # 指定告警查询的设备序列号(deviceID)
        update_interval = timedelta(minutes=5)

        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=update_interval,
        )

    def _persist_login_token(self) -> None:
        """Persist a token refreshed transparently by the API client."""
        token = self.ezviz_client.export_token()
        session_id = token.get(CONF_SESSION_ID)
        refresh_session_id = token.get(CONF_RFSESSION_ID)
        if not session_id or not refresh_session_id:
            return

        api_url = token.get("api_url", self.config_entry.data.get(CONF_URL))
        if (
            session_id == self.config_entry.data.get(CONF_SESSION_ID)
            and refresh_session_id == self.config_entry.data.get(CONF_RFSESSION_ID)
            and api_url == self.config_entry.data.get(CONF_URL)
        ):
            return

        data = {
            **self.config_entry.data,
            CONF_SESSION_ID: session_id,
            CONF_RFSESSION_ID: refresh_session_id,
            CONF_URL: api_url,
            CONF_USERNAME: self.config_entry.data.get(CONF_USERNAME),
            CONF_PASSWORD: self.config_entry.data.get(CONF_PASSWORD),
        }
        self.hass.config_entries.async_update_entry(self.config_entry, data=data)

    async def _async_load_cameras(self, *, refresh: bool = False) -> dict:
        """Load cameras from the API."""
        return await self.hass.async_add_executor_job(
            self.ezviz_client.load_cameras, refresh
        )

    async def _async_update_data(self) -> dict:
        """Fetch data from EZVIZ."""
        try:
            async with asyncio.timeout(self._api_timeout):
                try:
                    cameras = await self._async_load_cameras()
                except (EzvizAuthTokenExpired, EzvizAuthVerificationCode) as error:
                    raise ConfigEntryAuthFailed from error
                except (InvalidURL, HTTPError, PyEzvizError) as error:
                    if self.data is not None:
                        _LOGGER.warning(
                            "Keeping previous EZVIZ data after API error: %s",
                            _error_text(error),
                        )
                        return self.data
                    raise UpdateFailed(
                        f"Invalid response from API: {_error_text(error)}"
                    ) from error

                self._persist_login_token()
                return cameras

        except TimeoutError as error:
            if self.data is not None:
                _LOGGER.warning("Keeping previous EZVIZ data after API timeout")
                return self.data
            raise UpdateFailed("EZVIZ API request timed out") from error

    def setup_open_platform(
        self, app_key: str, app_secret: str, device_id: str | None = None
    ) -> None:
        """创建开放平台客户端(配置了 AppKey/Secret 才启用告警轮询)。"""
        self._open_platform = EzvizOpenPlatformClient(app_key, app_secret)
        self._alarm_device_id = device_id

    async def start_alarm_polling(self) -> None:
        """启动开放平台告警轮询后台任务。"""
        if self._open_platform is None or self._alarm_poll_task is not None:
            return
        self._alarm_poll_task = self.hass.loop.create_task(self._alarm_poll_loop())
        _LOGGER.warning("开放平台告警轮询已启动，间隔 %s 秒", ALARM_POLL_INTERVAL)

    async def stop_alarm_polling(self) -> None:
        """停止开放平台告警轮询后台任务。"""
        if self._alarm_poll_task is None:
            return
        self._alarm_poll_task.cancel()
        try:
            await self._alarm_poll_task
        except asyncio.CancelledError:
            pass
        self._alarm_poll_task = None

    async def _alarm_poll_loop(self) -> None:
        """告警轮询主循环：周期性查询新告警并触发事件。"""
        while True:
            try:
                await self._poll_alarms_once()
            except Exception:
                _LOGGER.exception("开放平台告警轮询异常")
            await asyncio.sleep(ALARM_POLL_INTERVAL)

    async def _poll_alarms_once(self) -> None:
        """查询自上次以来的新告警，触发 ezviz_cn_alarm 事件。"""
        if self._open_platform is None or not self.data:
            return

        now_ms = int(time.time() * 1000)

        # 首次轮询只建立游标，不触发历史告警
        if self._alarm_cursor_ms == 0:
            self._alarm_cursor_ms = now_ms
            return

        start_ms = self._alarm_cursor_ms

        # 配置了 deviceID 则只查该设备，否则遍历所有接入摄像头
        serials = [self._alarm_device_id] if self._alarm_device_id else list(self.data)
        for serial in serials:
            try:
                alarms = await self.hass.async_add_executor_job(
                    self._open_platform.get_alarm_list, serial, start_ms, now_ms
                )
            except PyEzvizError as err:
                _LOGGER.warning("查询 %s 告警失败: %s", serial, err)
                continue

            # 返回按 alarmTime 升序；逐个触发新告警
            for alarm in alarms:
                alarm_ts = int(alarm.get("alarmTime") or 0)
                if alarm_ts <= 0 or alarm_ts <= start_ms:
                    continue
                _LOGGER.warning(
                    "检测到新告警: serial=%s type=%s ch=%s name=%s",
                    serial,
                    alarm.get("alarmType"),
                    alarm.get("channelNo"),
                    alarm.get("alarmName"),
                )
                self.hass.bus.async_fire(
                    EVENT_ALARM,
                    {
                        "serial": serial,
                        "alarm_id": alarm.get("alarmId"),
                        "alarm_type": alarm.get("alarmType"),
                        "alarm_time": alarm_ts,
                        "channel_no": alarm.get("channelNo"),
                        "alarm_pic_url": alarm.get("alarmPicUrl"),
                        "alarm_name": alarm.get("alarmName"),
                    },
                )

        self._alarm_cursor_ms = now_ms


def _error_text(error: Exception) -> str:
    """Return a useful message even for exceptions without text."""
    return str(error).strip() or error.__class__.__name__
