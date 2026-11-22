# Universal Modbus 集成改动记录

本文档汇总本集成近期完成的全部改动，涵盖四大类：**前端与翻译中文化**、**原始写入服务**、**诊断传感器优化**、**设备状态诊断实体**。每项均列出改动文件、关键实现与设计要点，便于复核与后续维护。

> 相关文档：
> - [`write_register.md`](write_register.md) — 原始写入服务使用说明
> - [`LOCALIZATION_CHANGES.md`](LOCALIZATION_CHANGES.md) — 按功能细分的早期改动记录

---

## 目录

1. [前端与翻译中文化](#一前端与翻译中文化)
2. [新增 write_register 服务](#二新增-write_register-服务)
3. [诊断传感器优化](#三诊断传感器优化)
4. [新增设备状态诊断实体](#四新增设备状态诊断实体)
5. [翻译文件变更汇总](#五翻译文件变更汇总)
6. [改动文件总表](#六改动文件总表)
7. [校验结果](#七校验结果)

---

## 一、前端与翻译中文化

### 目标

让自带前端面板、添加设备向导、选项流程、诊断实体名称在中文环境下显示中文；英文、德文行为保持完全不变。

### 1.1 `frontend/profile-editor.js`（自带前端面板）

- 新增 **99 条中文词条字典 `ZH`**（英文原文 → 中文），覆盖按钮、表头、提示框、表单标签、公式帮助说明，以及原本硬编码的英文标签。
- `_t(en, de)` 扩展为 `_t(en, de, zh)`：
  - 新增 `_isZh()` 判断语言，匹配 `zh`、`zh-Hans`、`zh-CN` 等所有 `zh*` 开头的代码。
  - 中文环境优先使用第三参数 `zh`，否则从 `ZH` 字典回退；德文、英文原有逻辑不变。
- 新增 `_l(en)` 辅助方法，翻译原本不走 `_t()` 的硬编码标签：
  - 寄存器区域（0x01–0x10 Read/Write Coils/Registers 等）
  - 实体类型 `ToggleSwitch`
  - 写入模式 `Auto` / `Write Single/Multiple ...`
  - 字节序 `Big-Endian` / `Little-Endian`
  - `Read Only`、`None`、`Host`、`Port`、`Unit ID`、`Offset`、`Minimum`、`Maximum`、`Unit ` 前缀等
- 4 处带变量的文案补充中文第三参数：删除集线器、删除实体、清理孤立实体、副本命名。

### 1.2 `translations/zh.json` 与 `translations/zh-Hans.json`（新增）

- 与 `strings.json` 结构完全一致，`{manufacturer}`、`{model}`、`{description}`、`{config_entry}`、`{entities}`、`{entity}` 等占位符及页面链接原样保留。
- 同时建立两种文件名，兼容不同 HA 版本使用的语言代码。

---

## 二、新增 write_register 服务

### 目标

像 HA 自带 Modbus 集成一样，可在「设置 → 工具 → 动作」中执行原始寄存器写入命令。

```yaml
action: universal_modbus.write_register
data:
  hub: light_modbus_hub
  address: 1
  slave: 1
  value:
    - 1
    - 2
    - 3
    - 4
```

### 2.1 改动文件

| 文件 | 改动 |
| --- | --- |
| `const.py` | 新增常量 `SERVICE_WRITE_REGISTER = "write_register"`（第 25 行）。 |
| `coordinator.py` | 新增 `async_write_registers_raw()`（第 337 行）与底层同步写入方法，支持单值（FC06）/列表（FC16），`slave` 可覆盖，复用现有连接锁与操作锁。 |
| `__init__.py` | 注册 `universal_modbus.write_register` 服务（第 77 行）；`write_register()` 处理器（第 53 行）按集线器名称或配置条目 ID 定位 hub；用 voluptuous 校验参数。 |
| `services.yaml` | 新增 `write_register` 服务及字段描述（hub / address / slave / value）。 |
| 五个翻译文件 | 新增 `services` 段，提供英/德/中服务名与字段说明。 |
| `docs/write_register.md` | 新增服务使用文档。 |

### 2.2 设计要点

- 服务名为 `universal_modbus.write_register`，不能占用自带集成的 `modbus` 域。
- `hub` 同时支持名称与配置条目 ID，兼容性更好。
- 参数校验：`address` 0–65535、`slave` 0–255（上限 `MAX_UNIT_ID`）、`value` 为 0–65535 的整数或整数列表。
- 写入直接作用于寄存器，不依赖、不修改配置档案中的实体状态。

---

## 三、诊断传感器优化

### 3.1 「上次成功更新」退出活动面板

**问题**：HA 的「活动」(Logbook) 会自动隐藏带 `unit_of_measurement` / `state_class` 的连续传感器，但 `last_successful_update` 是纯 `TIMESTAMP` 传感器、无任何数值属性，每次轮询变化都写入活动面板。

**改动**（`sensor.py` 第 42 行）：给 `last_successful_update` 加空字符串单位 `native_unit_of_measurement=""`。

**原理**：Logbook 判断依据仅为属性键是否存在，不看值。空字符串单位不触发 TIMESTAMP 非数值设备类的校验、界面不可见、数据与显示完全不变，只是其变化不再写入活动面板。与「响应时间」「通信错误」两个诊断传感器机制一致。

---

## 四、新增设备状态诊断实体

### 目标

每个集线器自动创建一个诊断用 `binary_sensor`，`on` = 通讯正常、`off` = 设备离线；离线时仍保持 available，以便看到故障状态。

### 4.1 状态与属性

| 属性键 | 中文名 |
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

### 4.2 改动文件

| 文件 | 改动 |
| --- | --- |
| `coordinator.py` | 新增 `requests_sent`、`responses_received`、`last_error_time` 计数器（第 105–107 行）；`_record_exchange()`（第 292 行）在读/写/回读链路统一计数，`_set_last_error()`（第 298 行）统一记录错误信息与发生时间。 |
| `binary_sensor.py` | 新增 `UniversalModbusDeviceStatusSensor` 诊断实体（第 37 行）及注册；`is_on` 依据最近一轮轮询结果；`extra_state_attributes` 暴露 9 项属性。 |
| 五个翻译文件 | 新增 `entity.binary_sensor.device_status` 的名称、on/off 状态与 9 个属性名（英/德/中）。 |

### 4.3 设计要点

- 计数器在拿到 Modbus 响应时统一累加，无论响应是否 `isError()`（通讯层面设备确实回了响应）。
- `_read_feedback` 走 `_decode_batch` → `_read_batch`，反馈回读也自动计数。
- 错误信息与时间通过 `_set_last_error()` 统一赋值，避免散落重复代码。

---

## 五、翻译文件变更汇总

五个翻译文件始终保持键结构完全一致：

| 阶段 | 叶子键数 | 变化来源 |
| --- | --- | --- |
| 初始 `strings.json` | 164 | 基线（用户描述为 158，按实际文件对齐） |
| 新增 `services` 段后 | 180 | +16（两个服务的名称/描述/字段） |
| 新增设备状态实体翻译后 | 192 | +12（name / state×2 / state_attributes×9） |

涉及文件：`strings.json`、`translations/en.json`、`translations/de.json`、`translations/zh.json`、`translations/zh-Hans.json`。

---

## 六、改动文件总表

| 文件 | 涉及改动 |
| --- | --- |
| `frontend/profile-editor.js` | ① 中文化（99 条字典、`_t` 三参数、`_l` 硬编码标签、变量文案） |
| `translations/zh.json`（新增） | ① 中文翻译 ② 服务段 ④ 设备状态翻译 |
| `translations/zh-Hans.json`（新增） | ① 中文翻译 ② 服务段 ④ 设备状态翻译 |
| `translations/en.json` | ② 服务段 ④ 设备状态翻译 |
| `translations/de.json` | ② 服务段 ④ 设备状态翻译 |
| `strings.json` | ② 服务段 ④ 设备状态翻译（作为翻译模板基线） |
| `const.py` | ② 服务常量 |
| `coordinator.py` | ② 原始写入方法 ③ 通讯统计埋点 ④ 计数器 |
| `__init__.py` | ② 服务注册与参数校验 |
| `services.yaml` | ② 服务与字段描述 |
| `sensor.py` | ③ 上次成功更新退出活动面板 |
| `binary_sensor.py` | ④ 设备状态诊断实体 |
| `docs/write_register.md`（新增） | ② 服务使用文档 |
| `docs/LOCALIZATION_CHANGES.md`（新增） | ①③②④ 早期功能细分记录 |

---

## 七、校验结果

- **Python 语法**：`__init__.py`、`const.py`、`coordinator.py`、`sensor.py`、`binary_sensor.py` 全部 `py_compile` 通过。
- **JavaScript 语法**：`frontend/profile-editor.js` `node --check` 通过；97 个两参数 `_t()` 调用 + 3 条多行长文案全部命中字典；4 处变量文案均已覆盖。
- **翻译文件结构**：五个文件叶子键结构完全一致（各 192 键），占位符保留完整。
- **属性键对应**：`binary_sensor.device_status` 的 9 个属性键在代码与翻译间一一对应。
- **YAML**：`services.yaml` 解析通过，含 `write_register` 与 `export_profile` 两个服务。

> 应用所有改动后需**重启 Home Assistant 或重载集成**方可生效。
