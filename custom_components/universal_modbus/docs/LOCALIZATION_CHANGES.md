# 中文本地化与写入服务改动记录

本文档记录本集成近期所做的两类改动：界面/翻译的中文本地化，以及新增 `write_register` 服务。

## 一、中文本地化

### 1. `frontend/profile-editor.js`（自带前端面板）

- 新增 **99 条中文词条字典 `ZH`**（英文原文 → 中文），覆盖页面上的按钮、表头、提示框、表单标签、公式帮助说明，以及原本硬编码的英文标签。
- `_t(en, de)` 扩展为 `_t(en, de, zh)`：
  - 新增 `_isZh()` 判断语言，匹配 `zh`、`zh-Hans`、`zh-CN` 等所有 `zh*` 开头的代码。
  - 中文环境优先使用第三参数 `zh`，否则从 `ZH` 字典回退；德文、英文原有行为完全不变。
- 新增 `_l(en)` 辅助方法，翻译原本硬编码、不走 `_t()` 的英文标签：
  - 寄存器区域（0x01–0x10 Read/Write Coils/Registers 等）
  - 实体类型 `ToggleSwitch`
  - 写入模式 `Auto` / `Write Single/Multiple ...`
  - 字节序 `Big-Endian` / `Little-Endian`
  - `Read Only`、`None`、`Host`、`Port`、`Unit ID`、`Offset`、`Minimum`、`Maximum`、`Unit ` 前缀等
- 4 处带变量的文案补充中文第三参数：删除集线器、删除实体、清理孤立实体、副本命名。

校验：`node --check` 通过；97 个两参数 `_t()` 调用 + 3 条多行长文案全部命中字典；4 处变量文案均已覆盖。

### 2. `translations/zh.json` 与 `translations/zh-Hans.json`（新增）

- 让添加设备向导、选项流程、诊断实体名称显示中文。
- 与 `strings.json` 结构完全一致，`{manufacturer}`、`{model}`、`{description}`、`{config_entry}`、`{entities}`、`{entity}` 等占位符和页面链接原样保留。
- 两个文件名都建立，兼容不同 HA 版本使用的语言代码（`zh` 与 `zh-Hans`）。

> 注：最初描述中写「158 个键」，实际 `strings.json` 为 164 个叶子键，翻译文件按实际结构对齐。新增 services 段后为 180 个叶子键；再新增设备状态实体翻译后为 192 个叶子键。

## 二、新增 `write_register` 服务

目标：像 HA 自带 Modbus 集成一样，可在「设置 → 工具 → 动作」中执行原始寄存器写入命令。

### 改动文件

| 文件 | 改动 |
| --- | --- |
| `const.py` | 新增常量 `SERVICE_WRITE_REGISTER = "write_register"`。 |
| `coordinator.py` | 新增 `async_write_registers_raw()` 与 `_write_registers_raw()`，支持单值（FC06）/列表（FC16），`slave` 可覆盖，复用现有连接锁和操作锁；导入 `HomeAssistantError` 与 `MAX_UNIT_ID`。 |
| `__init__.py` | 注册 `universal_modbus.write_register` 服务；按集线器名称或配置条目 ID 查找条目；用 voluptuous 校验参数；导入 `vol` 与 `HomeAssistantError`。 |
| `services.yaml` | 新增 `write_register` 服务及其字段描述（hub / address / slave / value）。 |
| `strings.json`、`translations/en.json`、`translations/de.json`、`translations/zh.json`、`translations/zh-Hans.json` | 新增 `services` 段，提供英/德/中服务名与字段说明本地化。 |
| `docs/write_register.md` | 新增服务使用文档。 |

### 设计要点

- 服务名为 `universal_modbus.write_register`（不能占用自带集成的 `modbus` 域）。
- `hub` 同时支持名称与配置条目 ID，兼容性更好。
- 参数校验：`address` 0–65535、`slave` 0–255、`value` 为 0–65535 的整数或整数列表。
- 写入直接作用于寄存器，不依赖、不修改配置档案中的实体状态。

详细用法见 [write_register.md](write_register.md)。

## 三、诊断传感器增强

### 1. 「上次成功更新」退出活动面板

HA 的「活动」(Logbook) 会自动隐藏带 `unit_of_measurement` / `state_class` 的连续传感器。给 `last_successful_update`（`sensor.py`）加空字符串单位 `native_unit_of_measurement=""`：不触发 TIMESTAMP 非数值设备类的校验、界面不可见、数据与显示不变，只是其变化不再写入活动面板。与响应时间、通信错误两个诊断传感器机制一致。

### 2. 新增诊断实体「设备状态」(binary_sensor)

每个集线器自动创建一个诊断用 `binary_sensor`，`on` = 通讯正常、`off` = 设备离线；离线时仍保持 available，以便看到故障状态。

| 属性键 | 含义 |
| --- | --- |
| `requests_sent` | 发送次数 |
| `responses_received` | 收到次数 |
| `last_successful_update` | 上次通讯成功时间 |
| `host` | 设备 IP |
| `port` | 端口 |
| `communication_ok` | 通讯是否正常 |
| `last_error_time` | 上次错误时间 |
| `last_error` | 上次错误信息 |
| `communication_error_count` | 通讯错误次数 |

改动文件：

- `coordinator.py`：新增 `requests_sent`、`responses_received`、`last_error_time` 计数器；`_record_exchange()` 在读/写/回读链路统一计数，`_set_last_error()` 统一记录错误信息与发生时间。
- `binary_sensor.py`：新增 `UniversalModbusDeviceStatusSensor` 诊断实体及注册。
- `strings.json` 与四个翻译文件：新增 `entity.binary_sensor.device_status` 的名称、on/off 状态和 9 个属性名（英/德/中），叶子键增至 192。

### 校验

全部 Python 文件 `py_compile` 通过；五个翻译文件叶子键结构一致（各 192 键）。
