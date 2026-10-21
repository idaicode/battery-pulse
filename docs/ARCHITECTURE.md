# 实现笔记

这份文档记录"为什么这么写"，面向想改代码或移植到其它设备的人。
只想用的话看 [README](../README.md) 就够了。

---

## 1. 数据链路：两种设备两条完全不同的路

大部分"电量软件"只读电池驱动，读不到无线外设。这个项目的核心就是绕开驱动，直接跟设备说话。

### 1.1 罗技 G304 —— HID++ 2.0（走 2.4G 接收器）

1. 枚举 `VID_046D` 的 HID 设备，找到 `usage_page=0xFF00` 的两个 collection
   - `usage=1` → 短报文（report 0x10，7 字节）
   - `usage=2` → 长报文（report 0x11，20 字节）
   - **坑**：Windows 会把同一个接口的两个 collection 拆成两个句柄，短包写给长句柄会直接失败，必须分开配对。
2. 对设备索引 1–6 发 `getProtocolVersion`（feature `0x0000` / func 1）探测谁在线
3. 查 `feature 0x1000 BATTERY_LEVEL_STATUS`，响应第一个字节就是百分比
4. 用 `feature 0x0005 DEVICE_NAME` 拿型号名

实测返回 `[0x5A, 0x32, 0x00, ...]` → 90%。第二个字节这台固件塞的是私有值 `0x32`，不是标准状态码，所以充电状态改用第 3 字节的外部供电位判断。

代码：`core/hidpp.py`。换新鼠标先跑 `python tools/probe.py`，它会列出设备索引和支持的 feature。

### 1.2 RK98 —— BLE GATT（走蓝牙）

1. 用 PnP（`BTHLE\DEV_<MAC>`）列出在场蓝牙设备
2. WinRT `BluetoothLEDevice.from_bluetooth_address_async` 连上，读标准电池服务
   - Service `0x180F` / Characteristic `0x2A19` → 一个字节百分比
3. 关掉 GATT 会话，不影响键盘正常输入

**为什么不直接用 `bleak.BleakClient`**：设备已经连着 Windows，处于连接态不广播，`BleakClient` 的扫描前置会报 `DeviceNotFound`。必须用 WinRT 按地址直连。

代码：`core/ble.py`。

### 1.3 为什么 2.4G 模式下读不到 RK98

RK98 用的是国产 2.4G 方案（SINOWEALTH 系），接收器只把键盘事件转发成标准 HID 键盘报文，**没有暴露任何厂商电池页**——电量只有键盘自己的指示灯/驱动界面知道。切到 2.4G 后界面上这张卡会变灰并标注"2.4G 模式下读不到电量"。

要在软件里看到实时电量，让键盘走蓝牙通道。G304 没这个限制，它的 HID++ 本来就上报电量。

---

## 2. 托盘与自绘菜单

### 2.1 为什么不用原生 `TrackPopupMenu`

Windows 的普通菜单配色、圆角、字体全部不可定制，只会出来一块灰色方角面板，和面板那套米白/陶土色完全不搭。所以自己画：

- `WS_EX_LAYERED` + `UpdateLayeredWindow` → 逐像素透明，能做圆角卡片和投影
- 背景层 3~4 倍超采样后缩小画圆角，边缘干净；文字在目标分辨率直接绘制，不会糊
- 弹出只是贴一张位图，延迟 10ms 量级，没有额外进程、没有 WebView（实测 WebView2 新开窗口要 3.3 秒，销毁 2 秒，做菜单完全不可用）
- `+` / `−` 用 `ImageDraw.line()` 画线段而不是字形——微软雅黑缺 U+2212，用字符会渲染成豆腐块
- 开关是自绘的圆角轨道 + 白色滑块，不用系统 CheckBox

代码：`core/menu.py`、`core/tray.py`。

### 2.2 DPI：不能用 `GetDpiForSystem`

它受进程 DPI 感知模式影响：WebView2 先进场会把进程设成别的模式，此时返回 96，算出 `scale=1.0`，而系统实际按 1.5 显示——菜单按 1.0 渲染，点击坐标全错，表现为"菜单能弹但点不动"。

正确做法是 `GetDpiForMonitor`（直接问显示器，与进程模式无关），并在进程入口统一 `SetProcessDpiAwarenessContext(-4)`（Per-Monitor-V2）。

### 2.3 菜单是模态的，必须防重入

`show()` 内部自己跑 `GetMessageW` 循环，托盘窗口的消息仍会在这个循环里被取出、派发回 `_on_right`。不拦的话会嵌套建出第二个菜单，第一个失去 `_active` 引用——窗口没人管、ESC 和点击全失效，桌面上留一块永远关不掉的孤儿面板。

所以 `_on_right` 开头判断 `PopupMenu._active`，已开着就直接收起并返回。

### 2.4 图标注册会失败，必须重试

`Shell_NotifyIcon(NIM_ADD)` 在 explorer 刚重启、托盘服务没就绪时返回 `E_FAIL`。旧实现没检查返回值，失败也标记成"已添加"，之后每次同步都被"值没变就跳过"挡掉，图标永久消失（只能重启程序）。

现在失败不记账，每 1.5 秒重试一次、最多 30 次，覆盖 explorer 重启那几十秒的窗口期。

> ⚠️ 调试时不要用 `taskkill /f /im explorer.exe` 清幽灵图标。有些机器上 explorer 不会自动作为 shell 恢复（`AutoRestartShell=1` 也无效），`Shell_TrayWnd`/`Progman` 全无，`NIM_ADD` 一律失败。宁可留一个幽灵图标。

---

## 3. 面板窗口

### 3.1 它不是"把浏览器打包进去"

面板本质是一个网页（`ui/index.html`），但嵌在窗口里的 **WebView2**，不是系统浏览器。WebView2 是 Windows 自带的 Chromium 内核，装过 Edge 的 Win10 和 Win11 都有，所以 exe 里不需要带浏览器。

启动流程：

1. 绑定 `127.0.0.1:8731`（只监听本机）
2. 主线程 `webview.create_window(frameless=True)` 建无边框窗口
3. 窗口加载 `http://127.0.0.1:8731/` —— 界面和数据走本地 HTTP，网页代码一行不用改
4. 托盘在后台线程跑自己的 Win32 消息循环

### 3.2 一个足以让服务"假死"的死锁

「置顶」按钮调 `window.pywebview.api.set_on_top()`。pywebview 把 JS 调用丢到**新线程**执行，若该线程直接写 WinForms 属性（`on_top = true` → `i.TopMost`），会封送到 UI 线程；而 UI 线程挂着 pywebview 注册的 `timer.Tick += timer_tick`——那是 **Python 回调**，要跑必须先拿 GIL。GIL 正被卡在属性写入的线程持有 → 两边互等，永久死锁。

表现极具迷惑性：窗口正常显示过，随后整个 HTTP 服务假死——端口还在 `LISTENING`、连接堆在内核 backlog、CPU 0、日志无异常。实际所有 Python 线程都被冻住。

**修法**：窗口操作一律走 `ctypes` + HWND（`ShowWindow` / `SetWindowPos` / `PostMessage`）。`ctypes` 调用会释放 GIL，且是窗口管理器层面的操作，从任意线程调都安全。见 `core/desktop.py`。

**另一个坑**：`js_api` 对象的公开属性会被 pywebview 递归遍历（`webview/util.py :: get_functions`）。不要把 `Window` 挂成公开属性，否则它会顺着 `win.native` 摸进 WinForms/COM 对象图，逐层 `getattr` 触发跨套间 COM 读取，刷满 `[pywebview] Error while processing win.native...`。句柄用私有属性 `_hwnd`，自己用 `FindWindowW` 找。

### 3.3 点了「打开面板」没反应：三个独立原因

1. **Windows 前台锁**。只有当前持有前台窗口的进程才能调 `SetForegroundWindow`。托盘在后台跑，调用会被静默拒绝——窗口其实已 `ShowWindow` 出来，只是压在别的窗口下面。修法：`AttachThreadInput` 把本线程输入队列临时挂到前台线程，拿到合法前台权限后摘掉；万一还被拒，走一次 `HWND_TOPMOST → HWND_NOTOPMOST` 的 z 序闪现。
2. **找不到已存在的窗口**。纯托盘模式下打开面板是另起窗口进程，复用已有服务。原先是按 `IsWindowVisible` 筛——窗口被隐藏（点了关闭 = 收进托盘）就"找不到"，于是又起一个进程；而同一个 WebView2 用户目录不允许两开，第二个起不来，用户侧就是"没反应"。现在隐藏窗口也算数（只排除托盘隐藏消息窗），且 4 秒内不重复起进程。
3. **窗口标题撞车**。托盘那个 202×56 的隐藏消息窗标题也叫 "Battery Pulse"，`FindWindowW(None, title)` 会先命中它，之后 `ShowWindow`/`SetWindowPos` 全作用在它身上。现在用 `EnumWindows` + 类名排除 `BatteryPulseTrayWnd`。

### 3.4 位置与尺寸

- `MonitorFromWindow` 在后台线程会误判"不在任何显示器"，导致位置漂移（586,97 变 391,65）。改用 `MonitorFromRect` 判断矩形与显示器是否相交。
- `fit_size()` 按工作区封顶：150% 下 828 逻辑高 = 1242 物理，1080p 屏会顶穿任务栏。
- pywebview 的 `create_window(x=, y=)` 源码态有效、**打包后失效**，退回 Windows 级联位置。改成窗口可见后自己 `SetWindowPos` 居中，只做一次（hidden 启动时在首次 show 补做）。

---

## 4. 打包

产物是 onedir（目录式），不是 onefile：onefile 每次启动要把几十 MB 解压到临时目录，冷启动多 2–4 秒，对常驻工具不划算。

打包内容：

| 内容 | 作用 |
|---|---|
| Python 解释器 + 依赖 | `hidapi` / `bleak` / `pillow` / `pywebview` |
| `ui/index.html`、`ui/app.ico` | 界面 |
| `Microsoft.Web.WebView2.*.dll` | 托管 WebView2 的 .NET 桥接库 |
| `app.py` + `core/*.py` | 编译进 `pyz` 归档 |

运行时进程关系：

```
BatteryPulse.exe            Python 主进程：HTTP 服务 + 托盘 + 采集
  └─ msedgewebview2.exe ×N  WebView2 渲染进程（系统组件，不在打包内容里）
```

打包态用 `sys._MEIPASS` 区分：资源在 `_internal`（只读），配置/日志写在 exe 旁边，方便备份。

`ui/index.html` 是每次请求都重读的单文件，改完刷新窗口就生效，不用重新打包。

---

## 5. 性能与内存

| 项目 | 数值 |
|---|---|
| 常规常驻（轮询 5s，含托盘） | 约 45 MB |
| 点「释放内存」后 | **16–17 MB**（`EmptyWorkingSet` + `SetProcessWorkingSetSize`） |
| 低功耗模式 | 120s 轮询，每轮 `gc.collect()` |
| 托盘空闲 CPU | **0.0%**（消息循环阻塞在 `GetMessage`，无定时器） |
| 采集轮询 CPU | 单核 0.3% 以内 |

托盘为什么几乎不耗资源：

- 图标重绘由 `Manager` 采集完成后的回调触发（只投一个 `PostMessage`），没有独立定时器
- 只有「百分比 / 档位 / 提示文字」真的变了才重建 `HICON`
- 图标由 Pillow 画好一次后缓存（按 值+档位+尺寸 做 key），Pillow 延迟导入
- 全程一个进程、一个隐藏窗口；两个图标共用同一个消息循环

轮询节奏：

- 界面在前台 → 5 秒
- 界面关闭/切走超过 2 分钟 → 60 秒
- 打开低功耗 → 120 秒
- 读不到的蓝牙设备 → 45 秒内不重试（避免每轮卡在超时）
- 空闲 3 分钟且占用 > 32 MB 时静默回收（最多 5 分钟一次）

`winrt` 是延迟导入的：没有蓝牙设备时这部分模块根本不加载。

---

## 6. 诊断脚本

`tools/` 下都是可以单独跑的诊断程序，不是单元测试：

```bat
python tools\probe.py             :: 列出 HID++ 设备索引与支持的 feature
python tools\verify_tray.py       :: 图标是否真的进通知区域，打印 hr 和屏幕坐标
python tools\test_menu_click.py   :: 1.5x 缩放下的菜单命中测试
python tools\test_menu_lifecycle.py :: 菜单 ESC / 点外部 / 防重入
python tools\diag_panel.py        :: 打印面板窗口 class / rect / 可见性
python tools\preview_icons.py     :: 渲染图标矩阵到 shots\icons.png
python tools\render_menu.py       :: 离线渲染菜单三态，调样式不用启动程序
```
