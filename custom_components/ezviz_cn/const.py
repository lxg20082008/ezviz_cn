"""Constants for the EZVIZ CN integration."""

DOMAIN = "ezviz_cn"
MANUFACTURER = "EZVIZ"

# Configuration
ATTR_SERIAL = "serial"
CONF_FFMPEG_ARGUMENTS = "ffmpeg_arguments"
ATTR_TYPE_CLOUD = "EZVIZ_CLOUD_ACCOUNT"
ATTR_TYPE_CAMERA = "CAMERA_ACCOUNT"
CONF_SESSION_ID = "session_id"
CONF_RFSESSION_ID = "rf_session_id"
CONF_EZVIZ_ACCOUNT = "ezviz_account"
CONF_DEVICE_ID = "device_id"
CONF_APP_KEY = "app_key"
CONF_APP_SECRET = "app_secret"
# 兼容旧字段名（2026-11-03 早期版本，已迁移到 app_key/app_secret）
CONF_OPEN_PLATFORM_APP_KEY = "open_platform_app_key"
CONF_OPEN_PLATFORM_APP_SECRET = "open_platform_app_secret"

# Events
EVENT_ALARM = "ezviz_cn_alarm"

# Alarm polling (open platform)
ALARM_POLL_INTERVAL = 30  # 秒
# 告警抓拍图落盘目录(HA 容器内路径，宿主机 /mnt/shared/media/recordings/C7)
ALARM_PIC_DIR = "/media/recordings/C7"

# Services data
DIR_UP = "up"
DIR_DOWN = "down"
DIR_LEFT = "left"
DIR_RIGHT = "right"
ATTR_ENABLE = "enable"
ATTR_DIRECTION = "direction"
ATTR_SPEED = "speed"
ATTR_LEVEL = "level"
ATTR_TYPE = "type_value"

ATTR_X_AXIS = "x_axis"
ATTR_Y_AXIS = "y_axis"

# Service names
SERVICE_WAKE_DEVICE = "wake_device"
SERVICE_DETECTION_SENSITIVITY = "set_alarm_detection_sensibility"
SERVICE_PTZ_GO_COORDINATES = "ptz_go_coordinates"

# Defaults
CHINA_URL = "api.ys7.com"
EU_URL = "apiieu.ezvizlife.com"
RUSSIA_URL = "apirus.ezvizru.com"
DEFAULT_CAMERA_USERNAME = "admin"
DEFAULT_TIMEOUT = 25
DEFAULT_FFMPEG_ARGUMENTS = "/h264/ch1/main/av_stream"
