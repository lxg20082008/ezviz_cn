"""Support for EZVIZ button controls."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pyezvizapi import EzvizClient
from pyezvizapi.constants import SupportExt
from pyezvizapi.exceptions import HTTPError, PyEzvizError

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import EzvizConfigEntry, EzvizDataUpdateCoordinator
from .entity import EzvizEntity

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class EzvizButtonEntityDescription(ButtonEntityDescription):
    """Describe a EZVIZ Button."""

    method: Callable[[EzvizClient, str, str, int], Any]
    supported_exts: tuple[str, ...]


PTZ_ANY_CAPABILITIES = (
    str(SupportExt.SupportPtz.value),
    str(SupportExt.SupportPtzManualCtrl.value),
    str(SupportExt.SupportPtzNew.value),
)
PTZ_MODEL_HINTS = ("c6", "c6c", "c6n", "c6w", "c7", "c8", "cp1", "h6c")
PTZ_SPEED = 1  # 云台移动速度(1-8, 越大越快); 微调用最慢速
PTZ_HOLD_SECONDS = 0.3  # START 与 STOP 保持时长(秒), 决定单次移动幅度
BUTTON_NAMES = {
    "ptz_up": "云台上移",
    "ptz_down": "云台下移",
    "ptz_left": "云台左移",
    "ptz_right": "云台右移",
}


BUTTON_ENTITIES = (
    EzvizButtonEntityDescription(
        key="ptz_up",
        translation_key="ptz_up",
        method=lambda pyezviz_client, serial, run, channel: pyezviz_client.ptz_control(
            "UP", serial, run, speed=PTZ_SPEED, channel_no=channel
        ),
        supported_exts=(
            *PTZ_ANY_CAPABILITIES,
            str(SupportExt.SupportPtzTopBottom.value),
        ),
    ),
    EzvizButtonEntityDescription(
        key="ptz_down",
        translation_key="ptz_down",
        method=lambda pyezviz_client, serial, run, channel: pyezviz_client.ptz_control(
            "DOWN", serial, run, speed=PTZ_SPEED, channel_no=channel
        ),
        supported_exts=(
            *PTZ_ANY_CAPABILITIES,
            str(SupportExt.SupportPtzTopBottom.value),
        ),
    ),
    EzvizButtonEntityDescription(
        key="ptz_left",
        translation_key="ptz_left",
        method=lambda pyezviz_client, serial, run, channel: pyezviz_client.ptz_control(
            "LEFT", serial, run, speed=PTZ_SPEED, channel_no=channel
        ),
        supported_exts=(
            *PTZ_ANY_CAPABILITIES,
            str(SupportExt.SupportPtzLeftRight.value),
        ),
    ),
    EzvizButtonEntityDescription(
        key="ptz_right",
        translation_key="ptz_right",
        method=lambda pyezviz_client, serial, run, channel: pyezviz_client.ptz_control(
            "RIGHT", serial, run, speed=PTZ_SPEED, channel_no=channel
        ),
        supported_exts=(
            *PTZ_ANY_CAPABILITIES,
            str(SupportExt.SupportPtzLeftRight.value),
        ),
    ),
)


def _is_capability_enabled(value: Any) -> bool:
    """Return whether a supportExt value means enabled."""
    return str(value).lower() in {"1", "true", "yes"}


def _supports_button(
    support_ext: dict[str, Any] | None, capability_ids: tuple[str, ...]
) -> bool:
    """Return whether any capability id required by a PTZ button is enabled."""
    if not isinstance(support_ext, dict):
        return False

    return any(
        _is_capability_enabled(support_ext.get(capability))
        for capability in capability_ids
    )


def _looks_like_ptz_camera(camera_data: dict[str, Any]) -> bool:
    """Return whether model/name hints indicate an EZVIZ pan-tilt camera."""
    values = (
        camera_data.get("name"),
        camera_data.get("device_sub_category"),
        camera_data.get("device_type"),
        camera_data.get("device_model"),
        camera_data.get("model"),
    )
    camera_text = " ".join(str(value).lower() for value in values if value)
    return any(hint in camera_text for hint in PTZ_MODEL_HINTS)


def _supports_ptz_button(
    camera_data: dict[str, Any], capability_ids: tuple[str, ...]
) -> bool:
    """Return whether a camera should expose a PTZ button."""
    return _looks_like_ptz_camera(camera_data) or _supports_button(
        camera_data.get("supportExt"), capability_ids
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: EzvizConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up EZVIZ button based on a config entry."""
    coordinator = entry.runtime_data

    # Add button entities if supportExt indicates PTZ capability.

    async_add_entities(
        EzvizButtonEntity(coordinator, camera, entity_description)
        for camera in coordinator.data
        for entity_description in BUTTON_ENTITIES
        if _supports_ptz_button(
            coordinator.data[camera],
            entity_description.supported_exts,
        )
    )


class EzvizButtonEntity(EzvizEntity, ButtonEntity):
    """Representation of a EZVIZ button entity."""

    entity_description: EzvizButtonEntityDescription

    def __init__(
        self,
        coordinator: EzvizDataUpdateCoordinator,
        serial: str,
        description: EzvizButtonEntityDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, serial)
        self._attr_unique_id = f"{serial}_{description.key}"
        self._attr_name = BUTTON_NAMES.get(description.key, description.key)
        # entity_id 由 HA 2026.7 的英文翻译机制自动生成(如 button.c7_bc2840612_move_up),
        # 无需显式设置; 旧版 _attr_entity_id 已在此版本移除。
        self.entity_description = description

    def press(self) -> None:
        """Execute the button action."""
        try:
            # 双摄设备的云台在第 2 通道(长焦镜头), 单镜头云台机在第 1 通道。
            channel = 2 if self.data.get("supported_channels", 1) > 1 else 1
            self.entity_description.method(
                self.coordinator.ezviz_client, self._serial, "START", channel
            )
            # START 后保持片刻再 STOP, 否则云台移动时间过短(<200ms)肉眼不可见。
            time.sleep(PTZ_HOLD_SECONDS)
            self.entity_description.method(
                self.coordinator.ezviz_client, self._serial, "STOP", channel
            )
        except (HTTPError, PyEzvizError) as err:
            raise HomeAssistantError(
                f"Cannot perform PTZ action on {self.name}"
            ) from err
