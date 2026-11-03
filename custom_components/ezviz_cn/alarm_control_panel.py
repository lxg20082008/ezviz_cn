"""Support for Ezviz alarm."""

from dataclasses import dataclass
from datetime import timedelta
import logging

from pyezvizapi import PyEzvizError
from pyezvizapi.constants import DefenseModeType

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityDescription,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, MANUFACTURER
from .coordinator import EzvizConfigEntry, EzvizDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=60)
PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class EzvizAlarmControlPanelEntityDescription(AlarmControlPanelEntityDescription):
    """Describe an EZVIZ Alarm control panel entity."""

    ezviz_alarm_states: list


ALARM_TYPE = EzvizAlarmControlPanelEntityDescription(
    key="ezviz_alarm",
    ezviz_alarm_states=[
        None,
        AlarmControlPanelState.DISARMED,
        AlarmControlPanelState.ARMED_AWAY,
        AlarmControlPanelState.ARMED_HOME,
    ],
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EzvizConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Ezviz alarm control panel.

    中国区 api.ys7.com 不支持账号级 group 布防端点:
    - 读 get_group_defence_mode → /v3/userdevices/v1/group/defenceMode (404)
    - 写 api_set_defence_mode → /v3/userdevices/v1/group/switchDefenceMode (404)
    读、写全部不可用, 故不创建报警面板实体(否则 UI 上的布防按钮点了必报 404)。
    布防请用设备级 switch「布防」实体(switch.py 的 EzvizDefenceSwitch,
    走 /v3/devices/{serial}/1/changeDefenceStatusReq)。若将来萤石云开放 group
    端点, 恢复下方创建逻辑即可。
    """
    # 中国区 group 布防端点不可用, 不创建实体。
    # coordinator = entry.runtime_data
    # device_info = DeviceInfo(
    #     identifiers={(DOMAIN, entry.unique_id)},  # type: ignore[arg-type]
    #     name="EZVIZ Alarm",
    #     model="EZVIZ Alarm",
    #     manufacturer=MANUFACTURER,
    # )
    # async_add_entities(
    #     [EzvizAlarm(coordinator, entry.entry_id, device_info, ALARM_TYPE)]
    # )


class EzvizAlarm(AlarmControlPanelEntity):
    """Representation of an Ezviz alarm control panel."""

    entity_description: EzvizAlarmControlPanelEntityDescription
    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.ARM_HOME
    )
    _attr_code_arm_required = False

    def __init__(
        self,
        coordinator: EzvizDataUpdateCoordinator,
        entry_id: str,
        device_info: DeviceInfo,
        entity_description: EzvizAlarmControlPanelEntityDescription,
    ) -> None:
        """Initialize alarm control panel entity."""
        self._attr_unique_id = f"{entry_id}_{entity_description.key}"
        self._attr_device_info = device_info
        self.entity_description = entity_description
        self.coordinator = coordinator
        self._attr_alarm_state = None

    async def async_added_to_hass(self) -> None:
        """Entity added to hass."""
        self.async_schedule_update_ha_state(True)

    def alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command."""
        try:
            if self.coordinator.ezviz_client.api_set_defence_mode(
                DefenseModeType.HOME_MODE.value
            ):
                self._attr_alarm_state = AlarmControlPanelState.DISARMED

        except PyEzvizError as err:
            raise HomeAssistantError("Cannot disarm EZVIZ alarm") from err

    def alarm_arm_away(self, code: str | None = None) -> None:
        """Send arm away command."""
        try:
            if self.coordinator.ezviz_client.api_set_defence_mode(
                DefenseModeType.AWAY_MODE.value
            ):
                self._attr_alarm_state = AlarmControlPanelState.ARMED_AWAY

        except PyEzvizError as err:
            raise HomeAssistantError("Cannot arm EZVIZ alarm") from err

    def alarm_arm_home(self, code: str | None = None) -> None:
        """Send arm home command."""
        try:
            if self.coordinator.ezviz_client.api_set_defence_mode(
                DefenseModeType.SLEEP_MODE.value
            ):
                self._attr_alarm_state = AlarmControlPanelState.ARMED_HOME

        except PyEzvizError as err:
            raise HomeAssistantError("Cannot arm EZVIZ alarm") from err

    def update(self) -> None:
        """Fetch data from EZVIZ."""
        ezviz_alarm_state_number = "0"
        try:
            ezviz_alarm_state_number = (
                self.coordinator.ezviz_client.get_group_defence_mode()
            )
            _LOGGER.debug(
                "Updating EZVIZ alarm with response %s", ezviz_alarm_state_number
            )
            self._attr_alarm_state = self.entity_description.ezviz_alarm_states[
                int(ezviz_alarm_state_number)
            ]

        except PyEzvizError as error:
            _LOGGER.warning(
                "Could not fetch EZVIZ alarm status: %s "
                "(中国区 api.ys7.com 可能不支持 group defenceMode 端点)",
                error,
            )
            # 不 raise：避免 update 失败连锁导致 async_setup_entry 报错，
            # 报警面板状态保持未知即可。
