# EZVIZ CN Home Assistant 自定义集成

这是基于 Home Assistant 官方 `homeassistant/components/ezviz` 复制出来的自定义集成，域名改为 `ezviz_cn`，默认接入中国区萤石云 `api.ys7.com`，内置（vendored）CN 适配版 `pyezvizapi`，与官方 `pyezvizapi` 包互不冲突。

## 安装

1. 将 `custom_components/ezviz_cn` 放到 Home Assistant 配置目录的 `custom_components/ezviz_cn`。
2. 重启 Home Assistant。
3. 在「设置 -> 设备与服务 -> 添加集成」中搜索 `EZVIZ CN`。
4. 使用萤石云中国区账号登录，默认 URL 为 `api.ys7.com`。

## 登录与验证码（中国区特色）

- 萤石云中国区对「新终端首次登录」强制短信验证码：登录返回错误码 6002（硬件特征码校验失败）时，集成会**自动弹出验证码输入框**（"Verification code"），填入手机收到的短信码即可完成终端绑定。
- 同一终端（HA 主机）绑定过一次后，之后登录不再需要验证码。更换 HA 主机 / 重装系统后需重新验证。
- 该流程是官方国际版集成不具备的（官方 `ezviz` 的 config_flow 没有验证码步骤），为本集成针对中国区的重要增强。

## 中国区与官方版的差异（已适配）

| 项目 | 说明 |
| --- | --- |
| 登录 / 发码接口 | `api.ys7.com`；发验证码接口 `/v3/sms/nologin/checkcode`（带登录 headers，`bizType=TERMINAL_BIND`） |
| group defenceMode 端点 | 中国区返回 404，已容错：不再创建账号级报警面板实体（改用设备级布防 switch），仅警告一次不刷屏 |
| `async_setup_entry` | 返回 `bool`，对齐 HA 新版要求，不再报 `did not return boolean` |
| 设备属性 `supportExt` | 为空时不再崩溃（light / number / siren 等实体） |
| RTSP 连接测试 | 带 10 秒超时；网络不可达（如 Errno 113）会给出友好中文提示，不再报 "Unexpected exception" |

## 接入摄像头（本地 RTSP）

本集成通过**本地 RTSP** 拉流（不走萤石云中转），要求 HA 与摄像头在同一局域网二层网络。

### 1. 开启摄像头 RTSP 服务

萤石云视频 App 路径：

1. 「我的」→「工具」→「常用工具」→「局域网设备预览」→「开始扫描」
2. 选中摄像头，输入机身 6 位验证码进入
3. **双击视频画面进入预览**（关键一步：不双击看不到右上角设置入口）
4. 右上角齿轮 →「更多设置」→「本地服务开关」→ 打开 **RTSP**（建议同时打开 **HIK-SDK**）→ 保存，摄像头会自动重启
5. 「隐私设置」→ 关闭「视频加密」

> 注意：固件升级可能导致 RTSP 开关被复位，出现连不上时先回到这里确认开关状态。

### 2. 在 HA 中配置

集成会发现局域网内未配置的摄像头（弹窗提示），填写：

- **IP 地址**：摄像头实际局域网 IP
- **用户名**：`admin`
- **密码**：摄像头机身贴纸上的 6 位大写验证码（不是萤石云账号密码）
- **ffmpeg 参数**：`/h264/ch1/main/av_stream`（主码流；子码流用 `/h264/ch1/sub/av_stream`）

若摄像头视频编码为 H.265，参数改用 `/h265/ch1/main/av_stream`。

**双摄设备（如 C7 双摄）**：集成会自动为第二个镜头创建通道 2 实体（路径自动把 `ch1` 替换为 `ch2`，实体名「长焦」），无需手动配置。

### 3. 常见问题排查

| 现象 | 原因与处理 |
| --- | --- |
| `invalid_auth` | 验证码错误，或 RTSP 服务未开启。核对机身验证码；确认 App 里 RTSP 已开、视频加密已关 |
| `invalid_host` / `无法连接摄像头` | HA 到摄像头网络不通。检查摄像头是否与 HA 同一网段 / 广播域（摄像头连了二级路由或访客 Wi-Fi 时二层不通） |
| 实体正常但画面黑屏 | 视频编码为 H.265，改用 `/h265/ch1/main/av_stream`；或摄像头开了视频加密 |
| 萤石云上报的摄像头 IP 连不上 | 该 IP 可能已过期（DHCP 漂移 / 换过网络）。以路由器 DHCP 列表为准，或在 App「局域网设备预览」里看当前 IP |
| 摄像头实际 MAC 与萤石云上报 MAC 不一致 | 双频设备的无线连接 MAC 与云端上报 MAC 可能不同，属正常现象 |

## 布防 / 撤防（移动侦测）

每台接入的摄像头会自动创建一个 **switch 实体「布防」**（显示名「布防」，如 switch.c7_bc2840612_bu_fang），与萤石 App 的布防按钮等效：

- **布防**：开启移动侦测（有人移动即告警、推送）
- **撤防**：关闭移动侦测
- 状态实时回读自设备上报的 `alarm_notify`（STATUS.globalStatus）

底层走 App 客户端 API 设备级端点 `/v3/devices/{serial}/1/changeDefenceStatusReq`（中国区可用），与账号级布防端点（`/v3/userdevices/v1/group/*`，中国区返回 404）无关。无需开放平台（open.ys7.com）AppKey。账号级报警面板实体（走 group 端点）在中国区不可用，集成已不再创建。

## 移动侦测告警与本地录像（开放平台）

本集成可选接入**萤石开放平台**（open.ys7.com），实现「移动侦测触发 → 本地录制」：

1. 在萤石开放平台创建应用，把摄像头绑定到应用下
1. HA → 设置 → 设备与服务 → ezviz_cn → **配置（选项）**，填入开放平台 **AppKey / AppSecret**
1. 集成每 30 秒轮询告警，检测到新告警触发事件 **`ezviz_cn_alarm`**

事件携带字段：`serial`、`alarm_type`（10120=移动侦测/人体检测）、`alarm_time`（毫秒时间戳）、`channel_no`、`alarm_pic_url`、`alarm_name`。

自动化示例（检测到移动侦测 → `camera.record` 录制 30 秒）：

```yaml
automation:
  - alias: "萤石移动侦测本地录像"
    trigger:
      - platform: event
        event_type: ezviz_cn_alarm
        event_data:
          alarm_type: 10120
    action:
      - service: camera.record
        target:
          entity_id: camera.c7_bc2840612
        data:
          filename: "/media/recordings/motion_{{ now().strftime('%Y%m%d_%H%M%S') }}.mp4"
          duration: 30
          lookback: 10
```

录像保存到 `/media/recordings/`（宿主机 `/mnt/shared/media/recordings/`），可在 HA「媒体」里查看。

> 说明：萤石云 App 客户端 MQTT 推送（`push.ys7.com`）的中国区凭证已失效，故本功能改用开放平台告警查询 API，无需逆向 App。

## 云台（PTZ）控制

带云台的摄像头会自动生成 4 个方向按钮（云台上移/下移/左移/右移），点击一次移动一小段（约 0.3 秒）。单次移动幅度由 `speed`（云台速度，1 最慢）与 START/STOP 保持时长共同决定，代码常量 `PTZ_SPEED=1`、`PTZ_HOLD_SECONDS=0.3`，用于微调。双摄云台机（C7 等）的云台在第 2 通道（长焦镜头），单镜头云台机（C6/C8 等）在第 1 通道，集成会自动选择正确通道。底层走 App 客户端 API 设备级端点 `/v3/devices/{serial}/ptzControl`。

## 注意

- 不建议同时启用官方 `EZVIZ` 集成和本集成，因为两者都会安装同名 Python 包 `pyezvizapi`（本集成内置同名包并通过 `sys.modules` 注入，官方集成可能受影响）。
- 依赖包 `requests` / `pycryptodome` / `paho-mqtt` 由 HA 按 `manifest.json` 自动安装，无需手动处理。
