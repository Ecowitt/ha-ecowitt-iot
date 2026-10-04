"""Constants for the Ecowitt Official Integration."""

DOMAIN = "ha_ecowitt_iot"
CONF_VERSION = 2

CONF_MAC = "mac"
CONF_UPDATE_INTERVAL = "update_interval"
DEFAULT_UPDATE_INTERVAL = 10
CONF_FIRMWARE_CHECK = "firmware_check"
DEFAULT_FIRMWARE_CHECK = True

# 传感器身份映射持久化键（存于 config_entry.data）
# 映射形式：{ "Soilmoisture_ch1": "0xDFE4", ... }
CONF_SENSOR_ID_MAP = "sensor_id_map"

# 传感器 ID 的特殊值（无效/学习中/禁用）
SENSOR_ID_INVALID = "--"
SENSOR_ID_LEARNING = "FFFFFFFF"
SENSOR_ID_DISABLED = "FFFFFFFE"
SENSOR_ID_INVALID_VALUES = {
    SENSOR_ID_INVALID,
    SENSOR_ID_LEARNING,
    SENSOR_ID_DISABLED,
    "NONE",
    "N/A",
    "NA",
}