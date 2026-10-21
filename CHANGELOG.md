# 更新日志

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [SemVer](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-10-19

首个可用版本。

### 新增

- 罗技 HID++ 2.0 电量读取（G304 实测），短/长报文 collection 分开配对
- 蓝牙 GATT 电量读取（RK98 实测），走 WinRT 按地址直连，绕开"已连接不广播"时 `BleakClient` 扫描失败的问题
- 桌面面板：WebView2 无边框窗口 + 自绘标题栏，Claude 风格暖色界面
- 托盘常驻：一设备一图标，左键刷新、双击开面板、右键自绘菜单
- 米白圆角卡图标：电量数字 + 底部状态色进度条，按 `SM_CXSMICON` 自适应 16/24/32px
- 低电量分级提醒（阈值 / 临界两档，带静默期与回升重置）
- 开机自启（写 HKCU Run）、低功耗模式、工作集回收（45 MB → 16 MB）
- PyInstaller onedir 打包，产物不依赖本机 Python

### 修复

- 后台进程调用 `SetForegroundWindow` 被前台锁静默拒绝，导致「打开面板」看似无响应
- 托盘隐藏窗口与面板窗口同名，按标题查找时命中错误的窗口
- `Shell_NotifyIcon(NIM_ADD)` 失败后不重试，explorer 重启后图标永久消失
- pywebview 跨线程写 WinForms 属性与 `timer.Tick` 的 Python 回调互等，造成服务假死
- 150% 缩放下 `GetDpiForSystem` 返回 96，自绘菜单点击坐标全部落空
- 打包后 `create_window(x=, y=)` 被忽略，窗口不居中

### 已知限制

- RK98 在 2.4G 模式下读不到电量（接收器不暴露厂商电池页），需切蓝牙通道
- Windows 10 没有公开 API 能把托盘图标移出溢出区，首次需手动拖一次
