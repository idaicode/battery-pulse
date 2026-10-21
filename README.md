# Battery Pulse · 设备电量

[![build](https://github.com/yogurt/battery-pulse/actions/workflows/build.yml/badge.svg)](https://github.com/yogurt/battery-pulse/actions/workflows/build.yml)
[![release](https://img.shields.io/github/v/release/yogurt/battery-pulse)](https://github.com/yogurt/battery-pulse/releases/latest)
[![license](https://img.shields.io/github/license/yogurt/battery-pulse)](LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-3776AB)](pyproject.toml)

直接读取无线键鼠**真实电量**的 Windows 小工具。两种运行形态：

- **桌面面板**：无边框 WebView2 窗口，自绘标题栏，Claude 风格暖色界面（默认）
- **托盘常驻**：每只设备一个图标，右键是自绘弹层菜单，内存约 16 MB（自启用这个）

低于阈值弹系统通知。零控制台窗口，可以打包成不依赖 Python 的 exe。

![预览](shots/preview.png)

![托盘图标](shots/icons.png)

---

## 下载

不想装 Python 的话，直接去 [Releases](https://github.com/yogurt/battery-pulse/releases/latest)
下 `BatteryPulse-v*-win64.zip`，解压后双击 `BatteryPulse.exe`。

要求 Windows 10/11 + [WebView2 运行时](https://developer.microsoft.com/microsoft-edge/webview2/)（Win11 与装过新版 Edge 的 Win10 都已自带）。

---

## 快速开始

```bat
start.bat          :: 启动桌面面板（已在跑则把面板叫到前台）
tray-only.bat      :: 只起托盘，不建窗口（最省内存）
open-ui.bat        :: 唤起面板
stop.bat           :: 关闭

build.bat          :: 打包成 dist\BatteryPulse\BatteryPulse.exe
release.bat        :: 打包并压成可上传 Release 的 zip
```

从源码跑（三行）：

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\pythonw.exe app.py
```

托盘交互：

| 操作 | 行为 |
|---|---|
| **左键** | 立刻刷新一次（立刻重新读 HID++ / BLE，不等下一轮轮询） |
| **双击** | 打开 / 唤起面板 |
| **右键** | 弹出 Claude 风格弹层菜单 |
| 悬停 | 提示气泡：`G304 · 90% · 正常` |

![托盘菜单](shots/tray_menu.png)

菜单结构：

```
┌────────────────────────────────┐
│ G304 Lightspeed Wireless…   90% │  ← 设备名 + 档位色大数字
│ ● 正常 · 2.4G 接收器 · 刚刚同步  │
├────────────────────────────────┤
│ 打开面板                        │
│ 立即刷新                        │
│ 预警阈值          [-] 20% [+]   │
│ 系统通知                    (o) │
│ 提示音                      (o) │
│ 低功耗模式                  ( ) │
│ 开机自启                    (o) │
├────────────────────────────────┤
│ 退出托盘程序                    │
└────────────────────────────────┘
```

阈值和开关是**就地生效**的：点完原地重绘、菜单不关，能连着调；`打开面板` / `立即刷新` / `退出程序` 执行完自动收起。ESC 或点菜单外面关闭。`退出托盘程序` 会先摘掉图标，再把 HTTP 服务一起关掉，进程不残留。

### 为什么不用原生 `TrackPopupMenu`

Windows 的普通菜单配色、圆角、字体**全部不可定制**，只会出来一块灰色方角面板，和面板那套米白/陶土色完全不搭。所以这里自己画：

- `WS_EX_LAYERED` + `UpdateLayeredWindow` → 逐像素透明，能做圆角卡片和投影
- 背景层 3~4 倍超采样后缩小画圆角，边缘干净；文字在目标分辨率直接绘制，不会糊
- 弹出只是贴一张位图，延迟 10ms 量级，没有额外进程、没有 WebView（实测 WebView2 新开窗口要 3.3 秒，销毁 2 秒，做菜单完全不可用）
- `+` / `−` 是用 `ImageDraw.line()` 画的线段而不是字形——微软雅黑缺 U+2212，用字符会渲染成豆腐块
- 开关是自绘的圆角轨道 + 白色滑块，不用系统 CheckBox

### 两个必须知道的坑

**1. DPI 缩放不能用 `GetDpiForSystem`**

它受进程 DPI 感知模式影响：WebView2 先进场会把进程设成别的模式，此时它返回 96，算出 scale=1.0，而系统实际按 1.5 显示——菜单按 1.0 渲染，点击坐标全错，表现为"菜单能弹但点不动"。

正确做法是 `GetDpiForMonitor`（直接问显示器，与进程模式无关），并在进程入口统一 `SetProcessDpiAwarenessContext(-4)`（Per-Monitor-V2）。

**2. 菜单是模态的，必须防重入**

`show()` 内部自己跑 `GetMessageW` 循环，而托盘窗口的消息仍会在这个循环里被取出、派发回 `_on_right`。不拦的话会嵌套建出第二个菜单，第一个就失去 `_active` 引用——窗口没人管、ESC 和点击全部失效，桌面上留一块**永远关不掉的孤儿面板**。所以 `_on_right` 开头判断 `PopupMenu._active`，已开着就直接收起并返回。


| 文件 | 作用 |
|---|---|
| `start.bat` | 启动桌面面板（pythonw，无控制台窗口；已在运行则唤起面板） |
| `tray-only.bat` | 只起托盘，不创建 WebView2 窗口，内存最小 |
| `open-ui.bat` | 唤起面板（没在跑会先拉起来） |
| `build.bat` | 打包成独立 exe（见下一节） |
| `stop.bat` | 关闭后台服务（同时退出托盘） |
| `autostart-on.bat` / `autostart-off.bat` | 开 / 关开机自启（写 `HKCU\...\Run`，等价于托盘菜单里的那一项） |

环境：Python 3.10+，依赖只用到 `hidapi`、`bleak`、`pillow`、`pywebview`（见 `requirements.txt`）。建议装在项目内的 `.venv`，不污染系统 Python。

### 开机自启

写的是注册表而不是「启动」文件夹快捷方式——后者会先闪一个 cmd 黑框：

```
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
  BatteryPulse = "<...>\.venv\Scripts\pythonw.exe" "<...>\app.py" --tray
```

命令行也能改：`python app.py --autostart on|off|status`。

### 图标被折叠到 `^` 里了？

Windows 10 会把新来的托盘图标默认丢进溢出区，而且**没有公开 API 能提升它**（Win11 的 `NotifyIconSettings` 才能直接改）。首次启动时如果检测到图标在溢出区（`Shell_NotifyIconGetRect` 返回 `S_FALSE`），程序会弹一条提示。

**手动一次就行**：点任务栏的 `^`，把两个电量图标拖到任务栏上，Windows 会记住，以后一直在。

### 点了「打开面板」没反应？

这是两个独立原因叠在一起，现在都已修掉：

**1. Windows 的前台锁。** 只有**当前持有前台窗口的进程**才能调用 `SetForegroundWindow`。托盘在后台跑，它调这个 API 会被系统静默拒绝——窗口其实已经 `ShowWindow` 出来了，只是压在别的窗口下面，视觉上等于什么都没发生。修法是 `AttachThreadInput` 把本线程的输入队列临时挂到前台线程上，拿到合法的前台权限，成功后再摘掉；万一还被拒，就走一次 `HWND_TOPMOST → HWND_NOTOPMOST` 的 z 序闪现将窗口顶到最前。

**2. 找不到已存在的窗口。** 纯托盘模式下打开面板是另起一个窗口进程，复用已有服务。原先是按 `IsWindowVisible` 筛窗口的——窗口一旦被隐藏（点了面板上的关闭 = 收进托盘），就"找不到"，于是又起一个进程；而同一个 WebView2 用户目录**不允许两开**，第二个进程起不来，用户侧又是"没反应"。现在改成隐藏的窗口也算数（只排除托盘的隐藏消息窗），并且 4 秒内不重复起进程。

如果面板进程本身崩了，托盘会弹一条"面板正在打开…"的气泡，告诉你这次是在新起窗口（冷启动 WebView2 要几秒）。

### 托盘图标不见了？

`Shell_NotifyIcon(NIM_ADD)` 是**可能失败**的——explorer 刚重启、托盘服务还没就绪时它会返回 `E_FAIL`。旧实现没检查返回值，失败也照样把这一格标记成"已添加"，于是后续每次同步都被"值没变就跳过"的判断挡掉，图标就永久消失了（重启程序才能恢复）。

现在失败不记账，并每 1.5 秒重试一次、最多 30 次，覆盖 explorer 重启那几十秒的窗口期。


---

## 托盘图标

![图标](shots/icons.png)

米白圆角卡片 + 墨色电量数字 + 底部进度条。数字给精确值，横条给"还剩多少"的一眼可见量：

- 进度条颜色跟档位走：**正常=墨绿**、**偏低=琥珀**、**危急=砖红**、**离线=灰空槽**
- 浅色卡片在深色任务栏上很醒目；浅色任务栏上靠淡淡描边 + 深色数字拉开层次，两种主题都读得清
- 按 `SM_CXSMICON` 取实际尺寸渲染（100% 是 16px，150% 是 24px），8 倍超采样后缩小
- 数字宽度自适应，"100" 不会溢出卡片；低于 10% 时进度条至少留一个圆点，不会缩成看不见的细线


---

## 打包成 exe

### 它不是"把浏览器打包进去"

面板本质仍是一个网页（`ui/index.html`），但不是用系统浏览器打开的，而是嵌在窗口里的 **WebView2**。

WebView2 是 Windows 自带的 Chromium 内核，装了 Edge 的 Win10 和 Win11 都有。所以 exe 里**不需要带浏览器**，只需要：

| 打包内容 | 作用 |
|---|---|
| Python 解释器 + 依赖 | `hidapi` / `bleak` / `pillow` / `pywebview` |
| `ui/index.html`、`ui/app.ico` | 界面 |
| `Microsoft.Web.WebView2.*.dll` | 托管 WebView2 的 .NET 桥接库（几百 KB） |
| `app.py` + `core/*.py` | 编译进 `pyz` 归档 |

运行时的进程关系：

```
BatteryPulse.exe            Python 主进程：HTTP 服务 + 托盘 + 电量采集
  └─ msedgewebview2.exe ×N  WebView2 渲染进程（系统组件，不在打包内容里）
```

### 启动时发生了什么

1. 绑定 `127.0.0.1:8731`（只监听本机，局域网访问不到）
2. 主线程 `webview.create_window(frameless=True)` 建无边框窗口
3. 窗口加载 `http://127.0.0.1:8731/` —— 界面和数据走本地 HTTP，所以网页代码一行都不用改
4. 托盘在后台线程跑自己的 Win32 消息循环
5. 打包态用 `sys._MEIPASS` 区分：资源在 `_internal`（只读），配置/日志写在 exe 旁边，方便备份

### 一个足以让服务"假死"的死锁（已修）

界面上的「置顶」按钮调的是 `window.pywebview.api.set_on_top()`。pywebview 会把 JS 调用丢到**新线程**里执行，如果该线程直接写 WinForms 属性（`win.on_top = true` → `i.TopMost`），就会封送到 UI 线程；而 UI 线程上挂着 pywebview 注册的 `timer.Tick += timer_tick` —— 那是个 **Python 回调**，要跑起来必须先拿 GIL。可 GIL 正被这个卡在属性写入里的线程持有 → **两边互等，永久死锁**。

表现极具迷惑性：窗口正常显示过，随后整个 HTTP 服务"假死"——端口还在 `LISTENING`、连接堆在内核 backlog、CPU 占用 0、日志没有异常。实际上所有 Python 线程都被冻住了。

修法：窗口操作一律走 `ctypes` + HWND（`ShowWindow` / `SetWindowPos` / `PostMessage`），`ctypes` 调用会释放 GIL，且这些是窗口管理器层面的操作，不依赖 Python 回调，从任意线程调用都安全。`core/desktop.py` 里就是这么做的。

顺带一个坑：`js_api` 对象的**公开属性会被 pywebview 递归遍历**（`webview/util.py :: get_functions`）。所以不要把 `Window` 挂成公开属性，否则它会顺着 `win.native` 摸进 WinForms/COM 对象图，逐层 `getattr` 触发跨套间 COM 读取，刷出满屏 `[pywebview] Error while processing win.native...`。窗口句柄用私有属性 `_hwnd`，并且自己用 `FindWindowW` 找。


### 怎么打

```bat
build.bat
```

产物：

```
dist\BatteryPulse\
├─ BatteryPulse.exe          6 MB，双击运行
└─ _internal\               约 40 MB，运行时依赖（别删）
   ├─ ui\       界面
   ├─ webview\  WebView2 桥接 dll
   └─ pythonnet\ .NET 互操作
```

整个目录拷到任意 Windows 10/11 即可运行，不需要装 Python。

> 为什么是目录而不是单文件 exe：onefile 每次启动都要把 40 MB 解压到临时目录，冷启动会多 2–4 秒。这个程序是常驻的，onedir 更合适。

### 想改界面

`ui/index.html` 是**每次请求都重新读**的单文件，改完刷新窗口就生效，不用重新打包。改完再打一次 exe 即可带上。

---

## 它到底读了什么

这两只设备走的是**完全不同的两条链路**，这也是同类工具做不出来的原因——大部分"电量软件"只会读电池驱动，读不到无线外设。

### 罗技 G304 —— HID++ 2.0（走 2.4G 接收器）

1. 枚举 `VID_046D` 的 HID 设备，找到 `usage_page=0xFF00` 的两个 collection
   - `usage=1` → 短报文（report 0x10，7 字节）
   - `usage=2` → 长报文（report 0x11，20 字节）
   - 注意：Windows 会把同一个接口的两个 collection 拆成两个句柄，**短包写给长句柄会直接失败**，必须分开配对。
2. 对设备索引 1–6 发 `getProtocolVersion`（feature 0x0000 / func 1）探测谁在线
3. 查 `feature 0x1000 BATTERY_LEVEL_STATUS`，响应第一个字节就是百分比
4. 用 `feature 0x0005 DEVICE_NAME` 拿型号名

实测返回：`[0x5A, 0x32, 0x00, ...]` → 90%。第二个字节这台的固件塞的是私有值 `0x32`，不是标准状态码，所以充电状态改用第 3 字节的外部供电位判断——这是踩过的坑，写在代码注释里了。

### RK98 —— BLE GATT（走蓝牙）

1. 用 PnP (`BTHLE\DEV_<MAC>`) 列出在场蓝牙设备
2. WinRT `BluetoothLEDevice.from_bluetooth_address_async` 连上，读标准电池服务
   - Service `0x180F` / Characteristic `0x2A19` → 一个字节百分比
3. 关掉 GATT 会话，不影响键盘正常输入

实测：`40%`。

> 为什么不直接用 `bleak.BleakClient`？因为设备已经连着 Windows，处于**连接态不广播**，`BleakClient` 的扫描前置会报 `DeviceNotFound`。必须用 WinRT 按地址直连。

### 为什么 2.4G 模式下读不到 RK98

RK98 用的是国产 2.4G 方案（SINOWEALTH 系），接收器只是把键盘事件转发成标准 HID 键盘报文，**没有暴露任何厂商电池页**——电量只有键盘自己的指示灯/驱动界面知道。切到 2.4G 后，界面上这张卡会变灰并标注"2.4G 模式下读不到电量"。

想在软件里看到实时电量，让键盘走**蓝牙通道**（也就是截图里那个状态）。G304 没有这个限制，它的 HID++ 本来就把电量上报了。

---

## 低电量预警

- 阈值默认 20%，可拖到 5%–60%
- 跌破阈值提醒一次；继续跌到 10%（临界）再提醒一次
- 同一档位 30 分钟内不重复；任意两次提醒之间至少隔 60 秒
- 电量回升到「阈值 + 5%」以上才重置，避免在阈值边缘反复弹窗
- 通知走系统 Toast（`scenario="reminder"` 带提示音），掉不到就退化成 `MessageBeep`
- 可以在界面点「测试提醒」验证通道

---

## 内存与后台策略

界面关闭 / 页面切到后台后会自动降频，实测数据：

| 项目 | 数值 |
|---|---|
| 常规常驻（轮询 5s，含托盘） | 约 45 MB |
| 点「释放内存」后 | **16–17 MB**（`EmptyWorkingSet` + `SetProcessWorkingSetSize`，任务管理器立刻可见） |
| 低功耗模式 | 120s 轮询，每轮 `gc.collect()` |
| 托盘空闲 CPU | **0.0%**（消息循环阻塞在 `GetMessage`，不做任何定时器） |
| 采集轮询 CPU | 单核 0.3% 以内 |

托盘为什么几乎不耗资源：

- 图标重绘由 `Manager` 采集完成后的回调触发（只投一个 `PostMessage`），**没有独立定时器**
- 只有「百分比 / 档位 / 提示文字」真的变了才重建 `HICON`，否则一条消息就返回
- 图标由 Pillow 画好一次后缓存（按 值+档位+尺寸 做 key），Pillow 是延迟导入的
- 全程一个进程、一个隐藏窗口；两个图标共用同一个消息循环

轮询节奏：

- 界面在前台 → 5 秒
- 界面关闭/切走超过 2 分钟 → 60 秒
- 打开"低功耗" → 120 秒
- 读不到的蓝牙设备 → 45 秒内不再重试（避免每次轮询都卡在超时上）
- 空闲 3 分钟且占用 > 32 MB 时，自动做一次静默回收（最多 5 分钟一次）

`winrt` 是**延迟导入**的：没有蓝牙设备时，这部分模块根本不加载。


---

## 目录

```
battery-pulse/
├─ app.py                 HTTP 服务 + 路由（仅监听 127.0.0.1），--tray 常驻托盘
├─ core/
│  ├─ hidpp.py            HID++ 2.0 协议实现（短/长 collection 配对）
│  ├─ ble.py              WinRT GATT 电量读取 + PnP 发现
│  ├─ manager.py          轮询调度、预警状态机、内存指标、自动回收
│  ├─ tray.py             托盘：两个图标、左键刷新、右键弹菜单（纯 ctypes）
│  ├─ menu.py             Claude 风格弹层菜单（分层窗口 + Pillow 自绘）
│  ├─ desktop.py          WebView2 无边框窗口外壳（窗口操作走 ctypes）
│  ├─ autostart.py        开机自启（HKCU Run）
│  ├─ notify.py           Toast 通知
│  ├─ config.py           便携式配置（data/config.json，自动生成）
│  └─ winps.py            PowerShell 桥（-EncodedCommand，避免引号地狱）
├─ ui/index.html          单文件界面（无构建、无 CDN）
├─ tools/                 诊断与截图脚本（probe / verify_tray / test_menu_* …）
├─ shots/                 README 用的截图
├─ docs/PUBLISH.md        从本地文件到 GitHub 仓库的完整流程
├─ battery-monitor.spec   PyInstaller 配置（onedir）
├─ build.bat              打包 exe
├─ release.bat            打包 + 压成 Release 用的 zip
├─ pyproject.toml         元数据 / ruff / pytest
├─ CHANGELOG.md           版本变更
└─ CONTRIBUTING.md        开发与提交约定
```

## 参与

- 想改代码：看 [CONTRIBUTING.md](CONTRIBUTING.md)，环境三行就能跑起来
- 想发版 / 传 GitHub：[docs/PUBLISH.md](docs/PUBLISH.md) 有逐步命令
- 版本变更见 [CHANGELOG.md](CHANGELOG.md)

## 许可

[MIT](LICENSE)

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/state` | 设备列表 + 配置 + 内存指标（含 `tray_icons`） |
| POST | `/api/config` | `{warn_threshold, notify, sound, low_power}` |
| POST | `/api/refresh` | 立即采集 |
| POST | `/api/scan` | 重新发现蓝牙设备 |
| POST | `/api/trim` | 释放工作集 |
| POST | `/api/test-notify` | 发一条测试通知 |
| POST | `/api/shutdown` | 关服务并退出托盘（`stop.bat` 用的就是这个） |

## 排错

**界面显示"服务未响应"** —— 端口被占了。程序会自动顺延到 8732 起的空闲端口，看控制台输出或 `data/config.json` 里的 `port`。

**托盘没有图标** —— 先看界面底部「托盘 N 个」：显示 0 说明注册失败，跑 `.venv\Scripts\python.exe tools\verify_tray.py`，它会打印每个图标的 `hr` 和屏幕坐标。显示 2 但看不到，基本就是被折叠进 `^` 了，拖出来一次即可。

**图标是灰色的 `–`** —— 该设备离线。RK98 在 2.4G 模式下必然如此（见上），G304 则是接收器没插或鼠标没开。

**G304 不出现** —— 接收器要插着，且鼠标处于开机状态。换过接收器后跑一次 `python tools/probe.py`，能列出设备索引和支持的 feature。

**通知不弹** —— Windows 专注助手 / 勿扰模式会拦截 Toast；`CreateToastNotifier` 用的是未注册 AppID，部分系统会折叠到通知中心而不是横幅，事件列表里仍然有记录。

**新买了一只蓝牙外设** —— 界面点「扫描蓝牙」，会把它加进 `data/config.json` 的 `ble_devices`（只收真正暴露 0x180F 的设备）。

