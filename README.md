# 玉简 · Home Assistant 集成

[![一键添加到 HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=JochenZhou&repository=ha-yujian&category=integration)
[![打开 Home Assistant 添加集成](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=yujian)

把 [玉简](https://github.com/JochenZhou/TVNotify)（小米电视等 Android TV 上的局域网通知横幅 App）接入 Home Assistant。

电视端通过 mDNS 广播 `_yujian._tcp.local.`（旧版 App 的 `_tvnotify._tcp.local.` 也兼容），TXT 记录里带 `token` 与 `port`，所以这个集成**不需要手抄地址或扫码**：HA 起来后会自动发现电视、自动建好配置项，直接就能发通知。

| 能力 | 说明 |
| --- | --- |
| 自动发现 | mDNS `_yujian._tcp.local.`，TXT 携带 token / 版本 / 路径 / 型号 |
| 通知实体 | 标准的 `notify` 实体，可用 `notify.send_message` 定向发送 |
| 便捷服务 | `yujian.notify`（图片 / MJPEG / 方位 / TTS / 排队 / 幂等刷新）、`yujian.dismiss`、`yujian.set_config` |
| 状态回读 | 实体属性带 `muted`、`position`、`banner`，以及传音简录里上一条通知的内容与时间 |
| 失败自愈 | 电视端服务被系统杀掉时，自动经 ADB 拉起后重试一次 |
| 健康探活 | 轮询 `GET /health`，实体可用性与属性反映电视真实状态 |

---

## 安装

### 一键安装（HACS，推荐）

点上面第一个徽章即可，它会直接在你的 Home Assistant 里打开 HACS 的自定义存储库页面并填好仓库地址：

1. 点 **「一键添加到 HACS」** 徽章 → 浏览器会跳到你的 HA 实例（若未登录需先登录）
2. 确认仓库地址为 `https://github.com/JochenZhou/ha-yujian` → 点 **ADD**
3. 关闭弹窗，在 HACS 里搜索 **玉简** → 点 **下载**
4. **重启 Home Assistant**

### 手动添加存储库

HACS → 左侧「集成」→ 右上角「自定义存储库」→ 添加 `https://github.com/JochenZhou/ha-yujian` → 搜索 **玉简** → 下载 → 重启 HA。

### 手动安装

把 `custom_components/yujian` 整个目录放进 HA 的 `config/custom_components/` 下，重启 HA。

---

## 配置

电视端的玉简 App 需要先跑起来（它会广播 mDNS）。装好集成并重启 HA 后：

- 点上面第二个徽章 **「打开 Home Assistant 添加集成」** 可直接跳到配置页
- **设置 → 集成与设置 → 搜索「玉简」**，如果电视在线会直接出现在「发现」里，点一下即可
- 也可以点「添加集成」手动配置：**在 App 里点「复制调用地址」，把整条链接粘进第一个框**，IP、端口、Token 会自动拆出来（支持 `http://ip:8791/token/notify`、`…/token`、带尖括号或多余空格的粘贴）；也可以只填 IP 与 Token

配置完成后会得到一个通知实体，名字形如 `notify.yu_jian`。

> token 在电视上「重置 Token」后会变。电视重新广播时，集成会自动更新配置项里的 token，一般不需要手工干预。

### 选项：选一个 TTS 服务（想用语音播报才需要）

设置 → 设备与服务 → **玉简** → **配置**，在选项里选一个 `tts.*` 实体。选好之后，推送时勾选 `speak` 就会由 Home Assistant 合成语音，再把音频地址交给电视播放 —— 这条路径不依赖电视自己的语音引擎，安卓 6 电视也能出声。

**注意**：播放音频文件需要 App **v1.3.2 及以上**。旧版 App 会把音频地址当文本朗读（等于没声音），集成检测到版本过低会在日志里明确提示。

### 关于「自动发现」

mDNS 发现只做**发现**，不会替你装好：电视会出现在「发现」列表里，你点一下确认才真正建立配置项。这是 Home Assistant 对所有发现类集成的标准做法。

这样做的原因：Home Assistant 在**删除**一个通过 mDNS 发现的配置项后，会主动重新发现这台设备（好让你能重新添加）。如果发现就直接建条目，集成会在你删掉它的一瞬间自己装回来，根本删不掉。

所以删掉集成后，电视会重新出现在「发现」列表里 —— 想彻底关掉就点那条记录上的**「忽略」**，它就不会再出现了。

---

## 使用

### 定向发送到这台电视

```yaml
action: notify.send_message
target:
  entity_id: notify.yu_jian
data:
  title: 洗衣机已完成
  message: 晾晒提醒：衣服可以收了
```

### 用便捷服务（能带附加参数，UI 里可直接点选）

```yaml
action: yujian.notify
data:
  title: 暴雨红色预警
  message: 预计未来 3 小时降水量将达 100 毫米以上，请避免外出
  duration: 30
  level: error
  sticky: true
```

带图片或摄像头画面：

```yaml
action: yujian.notify
data:
  title: 门口有人
  message: 前门检测到移动
  image: http://192.168.101.20:8080/snapshot.jpg   # 图片 URL
  # image: /9j/4AAQSkZJRg...                        # 或 base64 内联（摄像头截图输出可直接粘进来）
  # video: http://192.168.101.20:8080/stream        # 或 MJPEG 流（约 15 帧/秒软解）
  duration: 15
```

| 参数 | 取值 | 说明 |
| --- | --- | --- |
| `title` | 字符串 | 标题，可留空 |
| `message` | 字符串 | 正文，最多四行 |
| `duration` | 1–30 秒 | 横幅停留时长，默认 5 |
| `level` | `info` / `warn` / `error` | 分级着色：白 / 琥珀 / 红 |
| `sticky` | 布尔 | 是否常驻不自动消失 |
| `max_duration` | 30–3600 秒 | 常驻兜底消失时间，默认 300 秒，防止横幅永久占屏 |
| `sound` | 布尔 | 是否播放入场提示音，默认开 |
| `image` | URL 或 base64 | 横幅上显示的图片；http(s) 地址按 URL 处理，其余按 base64 内联处理 |
| `video` | MJPEG 流 URL | 横幅上播放 MJPEG 流（multipart/x-mixed-replace）；不支持 mp4 等视频文件 |
| `position` | 六个方位 | `top` / `bottom` / `top-left` / `top-right` / `bottom-left` / `bottom-right`；留空沿用电视默认。四角是画中画小窗样式 |
| `speak` | 布尔 | 由集成用选项里选定的 TTS 服务合成音频再交给电视播放（需 App ≥ 1.3.2） |
| `tts` | 文本或音频地址 | 填文本让电视自己朗读（安卓 6 可能没中文语音）；填 http(s) 音频地址则直接播放该音频文件 |
| `queue` | 布尔 | 已有横幅在显示时，这条排队顺延播放，不抢占顶替 |
| `notify_id` | 字符串 | 同一标识再次推送时在原横幅上平滑更新文案与倒计时，不重新入场闪烁 |
| `image_interval` | 1–10 秒 | 仅对图片生效，按该间隔重新拉取图片地址，把静态快照变成准视频流 |

另有三个配套服务：

- `yujian.dismiss`（无参数）：立即关闭当前横幅，幂等。
- `yujian.set_config`：`muted`（闭关免扰，不弹横幅）/ `position`（电视端默认方位）/ `theme`（`xiuxian` 修仙玉简 / `default` tvOS 极简），三项可只改其一，改完立即回读电视真实状态。
- 实体属性会实时反映电视状态：`version`、`muted`、`position`、`banner`、`history_count`，以及上一条通知的 `last_title` / `last_text` / `last_level` / `last_has_media` / `last_notified_at`（来自 App 的「传音简录」）。

常用组合：

```yaml
# 门口有人：右下角小窗 + 语音播报 + 图片定时刷新
action: yujian.notify
data:
  title: 门口有人
  message: 前门检测到移动
  position: bottom-right
  tts: true
  image: http://192.168.101.20:8080/snapshot.jpg
  image_interval: 2
  duration: 20

# 洗衣机进度：同 id 高频刷新，不闪
action: yujian.notify
data:
  message: "洗涤中 {{ states('sensor.washer_progress') }}%"
  notify_id: washer-progress
  duration: 30
  sticky: true

# 多条消息依次播放，不互相顶掉
action: yujian.notify
data:
  message: 快递已放前台
  queue: true

# 语音播报：由 HA 合成，电视只负责播放（安卓 6 也能出声）
action: yujian.notify
data:
  title: 门口有人
  message: 前门检测到移动，请查看
  speak: true
  position: bottom-right

# 睡前打开闭关免扰并切回 tvOS 主题
action: yujian.set_config
data:
  muted: true
  theme: default
```

这些参数在 Home Assistant 的自动化编辑器里就是下拉框、数字滑块和开关，可以直接点选，不用手写 YAML。

### 自动化示例

```yaml
automation:
  - alias: "洗衣机完成 → 电视横幅"
    trigger:
      - platform: state
        entity_id: sensor.washer_status
        to: "finished"
    action:
      - action: yujian.notify
        data:
          title: 洗衣机已完成
          message: 晾晒提醒：衣服可以收了
          duration: 8
          level: info
          sticky: false
          sound: true
```

### 加入通知分组

集成是标准 `notify` 实体，可以直接放进 HA 的通知分组，之后用 `notify.notify` 一条消息同时发到手机和电视。

---

## 自愈机制

小米电视的省电策略经常在待机后杀掉后台服务，此时直接 POST 会连接失败。集成的处理是：

1. POST 失败 → 判定电视端服务不可用
2. 通过 [Android TV 集成](https://www.home-assistant.io/integrations/androidtv/) 的 `androidtv.adb_command` 执行 `am startservice -n com.zqc.tvnotify/.NotifyService` 把 App 拉起来
3. 等 2 秒让服务绑定 8791 端口，重试一次 POST

前提：HA 已配置 Android TV 集成（对这台电视有 ADB 授权），且电视的 ADB 授权没被清掉。没有 Android TV 集成时，推送仍然可用，只是服务被杀后不会自愈。

---

## 故障排查

| 现象 | 排查 |
| --- | --- |
| 集成没发现电视 | 电视端 App 是否在跑（mDNS 随服务一起停）；HA 是否与电视同一网段；HA 容器是否 host 网络 |
| 实体 unavailable | 电视是否开机、`GET http://<电视IP>:8791/health` 是否通 |
| 通知没出现 | `appops get com.zqc.tvnotify SYSTEM_ALERT_WINDOW` 应为 `allow` |
| 提示不响 | 电视端 App 设置里静音，或请求体带 `"sound": false` |

---

## 许可

MIT，见 [LICENSE](LICENSE)。
