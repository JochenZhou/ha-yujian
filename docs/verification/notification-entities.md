# 玉简通知实体升级验证记录

实现版本：1.4.0（本地构建，未发布）

对照 App：YuJian v1.9.0，提交 `f29bab009d64ddfbc8317ffb80cfbc81d58394ca`。

## 验证环境与边界

使用临时隔离的 Home Assistant 2026.10.4 容器，以及实现 App 通知 HTTP 协议的两台本地模拟设备。未向真实电视发送通知、执行 ADB 或修改设置；未修改生产 HA，原测试 HA 保持停止状态。

模拟设备验证可以证明 HA 的实体注册、服务调用、目标路由、协议载荷、状态回读和配置链接工作正常。真实电视上的横幅渲染、声音、媒体下载/解码与实际手机浏览器跳转仍需设备验收，不能由模拟结果替代。

## 运行结果

- 客户端协议回归：12 项通过（`tests/test_client.py`，真实 aiohttp 服务收发）。
- 基础 HA 联调：47 项通过，覆盖两台设备各十个实体、九套主题、六个位置、静音、通知/关闭/设置服务、标题或媒体单独发送、历史媒体字段、失败反馈、刷新与恢复。
- 扩展 HA 联调：22 项通过，覆盖设备与区域目标、默认广播、语音参数兼容、中英文翻译、选项保存、默认时长、Token 轮换、访问链接及实体/设备 ID 保留。
- 升级回归：5 项通过，覆盖标准通知空内容拦截、发送后即时刷新、旧 options 默认时长保留、旧 Token 不再遮蔽重发现、测试选项恢复。
- 启动离线后自然轮询恢复：通过，未手动刷新。
- 旧布尔语音模式在缺少 TTS 时：横幅仍发送，并向调用方报告部分失败；通过。
- 新主题中文名称与 App 对齐：通过。
- Ruff lint、格式校验、Python 编译、模块未定义名检查、JSON/YAML 解析、源翻译与英文文件一致性、git diff 空白检查：通过。

## 可重复运行

在提供 Home Assistant 依赖的 Python 环境中，从仓库根目录运行：

```bash
python -m unittest discover -s tests -v
python -m compileall -q custom_components/yujian
python scripts/check_names.py custom_components/yujian/*.py
ruff check custom_components/yujian tests
ruff format --check custom_components/yujian tests
git diff --check
```

HA 联调使用独立配置、临时测试用户和两个本地 mock App，不使用线上凭据。脚本和原始结果保留于本次工作目录的隔离测试路径；安装包不包含测试配置或凭据。
