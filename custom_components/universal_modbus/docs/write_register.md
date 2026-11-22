# write_register 服务使用文档

`universal_modbus.write_register` 允许你直接从 Home Assistant 向 Universal Modbus 集线器背后的设备写入保持寄存器原始值，行为与 Home Assistant 自带的 Modbus 集成的 `modbus.write_register` 类似。

你可以在「设置 → 工具 → 动作」中选择该动作并填写表单，或在自动化、脚本、开发者工具中直接用 YAML 调用。

> 说明：服务名是 `universal_modbus.write_register`，而不是 `modbus.write_register`。后者属于 HA 自带的 Modbus 集成，本集成使用自己的域名 `universal_modbus`。

## 基本用法

### 写入单个寄存器（FC06）

```yaml
action: universal_modbus.write_register
data:
  hub: light_modbus_hub
  address: 1
  slave: 1
  value: 1
```

### 写入多个连续寄存器（FC16）

当你贴出的 `value` 是一个列表时，会从 `address` 开始依次写入多个寄存器：

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

上例表示：向从站 `1` 的保持寄存器 `1、2、3、4` 分别写入 `1、2、3、4`。

## 参数说明

| 参数 | 必填 | 类型 | 说明 |
| --- | --- | --- | --- |
| `hub` | 是 | 字符串 | 目标集线器。可以是集成中显示的**集线器名称**（如 `light_modbus_hub`），也可以是该集线器的**配置条目 ID**。 |
| `address` | 是 | 整数 (0–65535) | 起始保持寄存器地址。 |
| `slave` | 否 | 整数 (0–255) | Modbus 单元/从站 ID。留空时使用集线器配置的默认单元 ID；可用于访问同一网关后的其他设备。 |
| `value` | 是 | 整数或整数列表 (每项 0–65535) | 单个值按 FC06（写单个寄存器）发送；值列表按 FC16（写多个寄存器）发送到连续地址。 |

## 行为说明

- **无需配置实体**：该服务直接向寄存器写入原始值，不依赖配置档案里是否定义了对应实体，也不会修改实体的状态缓存。
- **写入模式**：单个整数值 → FC06 (`Write Single Register`)；整数列表 → FC16 (`Write Multiple Registers`)。
- **连接与并发**：复用集线器现有的 Modbus TCP 连接、连接锁与操作锁，与轮询读取互不冲突。写入失败时会自动关闭连接并在下次操作时重连。
- **slave 优先级**：显式传入的 `slave` 仅对本次写入生效，不改变集线器配置。
- **错误返回**：未知集线器、集线器未加载、参数越界或 Modbus 设备返回错误时，动作会抛出错误，可在自动化中据此做失败处理。

## 在自动化 / 脚本中使用示例

```yaml
alias: 写入灯光亮度寄存器
trigger:
  - platform: state
    entity_id: input_number.light_level
action:
  - action: universal_modbus.write_register
    data:
      hub: light_modbus_hub
      address: 1
      slave: 1
      value: "{{ states('input_number.light_level') | int }}"
mode: single
```

## 查找集线器名称与配置条目 ID

- **集线器名称**：在集成的「Universal Modbus」面板顶部，或添加设备时填写的名称（对应配置条目的标题）。
- **配置条目 ID**：在「设置 → 设备与服务 → Universal Modbus」中进入对应条目，浏览器地址栏 URL 里的 `config_entry` 参数即为条目 ID。
