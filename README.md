# 玉简 · Home Assistant 集成

[![一键添加到 HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=JochenZhou&repository=ha-yujian&category=integration)
[![添加集成](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=yujian)

将 [玉简 Android TV App](https://github.com/JochenZhou/TVNotify) 的局域网横幅通知接入 Home Assistant。保留标准 `notify` 实体和已有服务，增加设备设置与状态实体。

## 安装与连接

要求 **Home Assistant 2026.10.0 及以上**；九套主题建议搭配玉简 App v1.9.0。

1. 在电视上启动玉简，开启悬浮窗权限，确保 HA 与电视网络互通。
2. 通过上方 HACS 徽章添加仓库，下载集成并重启 Home Assistant。也可将 `custom_components/yujian` 复制到 HA 的 `config/custom_components/` 后重启。
3. 进入 **设置 → 设备与服务**，在「已发现」中确认添加玉简。支持 `_yujian._tcp.local.` 和旧版 `_tvnotify._tcp.local.`；发现后需要用户确认，不会自动安装。
4. 未发现时，手动添加「玉简」，粘贴 App 中复制的调用地址，如 `http://192.168.1.5:8791/abc123/notify`；也可分别填写 IP、端口和 Token。

设备实体可直接加入仪表盘。实际实体 ID 以设备页为准，下文的 ID 均为示例。

## 设备控制与状态

| 实体 | 用途 |
| --- | --- |
| `notify` 通知 | 通过 `notify.send_message` 定向发送标题和正文，保留原有通知实体 |
| `switch` 通知静音 | 关闭提示音与 TTS 语音播报；**横幅仍然显示** |
| `select` 主题 | 设置设备默认主题，支持下表九种主题 |
| `select` 默认显示位置 | 顶边、底边或四角，共六个位置 |
| `button` 关闭横幅 | 立即关闭当前横幅 |
| `button` 刷新状态 | 立即重新读取设备状态 |
| `binary_sensor` 横幅显示中 | 当前是否正在显示横幅 |
| `sensor` 最近通知 | 状态是通知时间戳；属性包含 `title`、`text`、`level`、`position`、`has_media`、`sticky` |
| `sensor` 通知历史条数 | App 返回的通知历史数量 |
| `sensor` 服务运行时间 | 诊断传感器，时长值以秒为单位 |

集成轮询设备健康与通知历史。无法读取状态时实体会显示不可用；设备恢复后继续更新。

设备页的 **访问** 按钮直接打开 App 自带的 WebUI：`http://<电视IP>:<端口>/<Token>/ui`。这是浏览器直接访问电视，因此手机或电脑也必须能连接电视局域网；通过 HA 的远程地址访问 HA 并不代表浏览器能访问电视。WebUI 地址包含 Token，请勿分享。发现新的地址或 Token 后，设备入口随连接信息更新。

| 主题 ID | 名称 |
| --- | --- |
| `xiuxian` | 修仙玉简 |
| `default` | tvOS 极简 |
| `palace` | 大唐鎏金 |
| `cyberpunk` | 赛博霓虹 |
| `wukong` | 黑神话·暗金 |
| `matrix` | 极客终端 |
| `ink_light` | 江南宣纸 |
| `gamer` | 主机奖杯 |
| `minecraft` | 方块世界 |

新主题的显示效果取决于电视端 App 版本。服务和实体使用以上固定 ID；界面标签提供中文和英文翻译。

## 发送通知

普通文字通知使用标准动作：

```yaml
action: notify.send_message
target:
  entity_id: notify.yu_jian
data:
  title: 洗衣机已完成
  message: 衣服可以晾晒了
```

带媒体、单次主题或语音时使用 `yujian.notify`。在自动化编辑器中可以直接选择字段：

```yaml
action: yujian.notify
target:
  entity_id: notify.yu_jian
data:
  title: 门口有人
  message: 前门检测到移动
  image: http://192.168.1.20:8080/snapshot.jpg
  image_interval: 2
  position: bottom-right
  theme: cyberpunk
  duration: 15
  speak: ha
```

`yujian.notify` 的正文可省略，标题、正文、图片、视频至少提供一项。例如只发送图片：

```yaml
action: yujian.notify
target:
  entity_id: notify.yu_jian
data:
  image: http://192.168.1.20:8080/snapshot.jpg
```

| 参数 | 说明 |
| --- | --- |
| `title` / `message` | 标题 / 正文；正文最多四行 |
| `duration` | 1–30 秒；省略时使用集成选项中的默认时长 |
| `theme` | 仅本次通知的主题；省略时使用设备默认，不修改全局主题 |
| `position` | `top`、`bottom`、`top-left`、`top-right`、`bottom-left`、`bottom-right`；省略时使用设备默认 |
| `level` | `info`、`warn`、`error` |
| `sticky` / `max_duration` | 常驻开关 / 常驻兜底时长（30–3600 秒，默认 300） |
| `sound` | 入场提示音，默认开启；设备静音时不播放 |
| `image` | HTTP(S) 图片地址或 base64 内容；电视需能访问图片地址 |
| `video` | MJPEG 流地址，类型为 `multipart/x-mixed-replace`；不支持 MP4 等视频文件 |
| `image_interval` | 每 1–10 秒重新拉取图片地址，仅用于图片 |
| `speak` | `off`（默认）、`ha`、`tv`；旧布尔写法 `true` 等于 `ha`，`false` 等于 `off` |
| `queue` | 排队到当前通知之后显示 |
| `notify_id` | 使用相同标识更新现有横幅文案与倒计时，适合进度提醒 |

`yujian.notify`、`yujian.dismiss`、`yujian.set_config` 支持 HA 标准实体、设备和区域目标；选择实体时选择此集成的 `notify` 实体。**不指定目标时作用于所有已配置的玉简设备。**

### 语音与静音

使用 `speak: ha` 前，进入 **设置 → 设备与服务 → 玉简 → 配置**，选择一个 `tts.*` 实体。HA 合成标题与正文，电视下载并播放生成的音频，需要电视能访问 HA 的音频地址，且 App 版本至少为 1.3.2。

`speak: tv` 使用电视自身的 TTS 引擎，效果取决于电视安装的语音。`speak: off` 只关闭语音，提示音由 `sound` 决定。设备「通知静音」开启后，提示音与语音都关闭，横幅照常显示。

### 修改默认设置与关闭横幅

通常直接操作设备页中的静音开关、主题和位置选择器即可。自动化也可使用已有服务：

```yaml
action: yujian.set_config
target:
  entity_id: notify.yu_jian
data:
  muted: true
  theme: ink_light
  position: top
```

只传需要修改的字段，其他设备设置保持原值。

```yaml
action: yujian.dismiss
target:
  entity_id: notify.yu_jian
```

## 故障排查

| 现象 | 检查 |
| --- | --- |
| 没有发现设备 | App 服务是否运行，mDNS 是否能到达 HA，容器网络是否支持组播；也可手动添加 |
| 实体不可用 | 电视是否开机，HA 能否访问 `http://<电视IP>:8791/health` |
| 没有横幅 | App 悬浮窗权限是否开启；确认调用目标与服务返回的错误 |
| 没有声音 | 设备静音、`sound`、`speak`、HA TTS 配置、音频地址可达性及电视语音引擎 |
| 「访问」打不开 | 当前浏览器所在网络能否直接连接电视 IP、端口，Token 是否有效 |

推送遇到连接故障时，集成可通过已配置并授权的 Android TV 集成调用 ADB 拉起 `com.zqc.tvnotify/.NotifyService` 后重试。未配置 Android TV 时仍可正常推送，但无法使用此恢复方式。刷新状态只读取设备，不触发 ADB 拉起。

删除集成后，在线设备可能重新出现在「已发现」列表；选择「忽略」即可隐藏发现提示。
