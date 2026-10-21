# 参与开发

## 1. 环境

Windows 10/11 + Python 3.10 以上。不需要 Node、不需要前端构建工具——界面就是一个 html 文件。

```bat
git clone https://github.com/idaicode/battery-pulse.git
cd battery-pulse

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
```

VS Code 里按 `Ctrl+Shift+P` → `Python: Select Interpreter` → 选 `.venv\Scripts\python.exe`。
仓库自带 `.vscode/` 配置，打开即可直接 F5 调试。

## 2. 三种跑法

| 命令 | 用途 |
|---|---|
| `python app.py` | 面板 + 托盘，日常开发 |
| `python app.py --tray` | 只起托盘，改图标/菜单用这个（省内存） |
| `python app.py --no-open` | 只起 HTTP 服务，用浏览器开 `http://127.0.0.1:8731` 调界面 |

改 `ui/index.html` 后**刷新窗口**即可，它是每次请求都重读的。改 `core/*.py` 要重启进程——Python 没有热重载，这个是刻意的。

## 3. 改代码前先看这两条

- **所有窗口操作走 `ctypes` + HWND**，不要在线程里碰 pywebview / WinForms 的属性。原因见 README「一个足以让服务假死的死锁」。
- **新增公开属性要小心**：`js_api` 对象会被 pywebview 递归遍历公开属性，挂 Window 进去会摸到 COM 对象图并刷屏报错。句柄一律用 `_hwnd` 这类私有名字。

## 4. 工具脚本

`tools/` 下的脚本都是可以单独跑的诊断程序，不是单元测试：

```bat
python tools\probe.py             :: 列出 HID++ 设备索引与支持的 feature，换新鼠标先跑它
python tools\verify_tray.py       :: 图标真的进通知区域了吗，打印 hr 和屏幕坐标
python tools\test_menu_click.py   :: 1.5x 缩放下菜单的命中测试
python tools\diag_panel.py        :: 打印面板窗口的 class / rect / 可见性
python tools\preview_icons.py     :: 渲染图标矩阵到 shots\icons.png
```

## 5. 提交

提交信息用 Conventional Commits，一眼能看出改了什么：

```
feat(hidpp): 支持 feature 0x1004 的电压读数
fix(tray): NIM_ADD 失败后重试，避免图标永久消失
docs: 补充 RK98 在 2.4G 模式下的限制
chore: 升级 pyinstaller
```

三种提交方式，任选：

| 方式 | 操作 |
|---|---|
| VS Code 图形界面 | 左侧「源代码管理」→ 填消息 → `Ctrl+Enter` 提交（仓库已配置提交后自动推送） |
| 命令行 | `git add -A && git commit -m "..." && git push` |
| 双击脚本 | `push.bat`（自动生成带时间戳的消息）或 `push.bat "fix: xxx"` |

提交前跑：

```bat
ruff check .
ruff format --check .
```

PR 描述里写清楚**在什么设备、什么 Windows 版本、什么缩放下验证过**——这个项目的 bug 大量集中在 DPI 和窗口管理上，没有这些信息没法 review。

## 6. 新增设备支持

- **罗技**：先 `python tools\probe.py`，确认能枚举到设备索引，再看 `BATTERY_LEVEL_STATUS (0x1000)` 是否在 feature 列表里。
- **蓝牙**：标准电池服务是 `0x180F` / `0x2A19`，能把百分比读出来的设备，界面上点「扫描蓝牙」就能加。
- **2.4G 国产方案**（如 RK98 的 SINOWEALTH 接收器）大多只转发 HID 键盘报文，没有厂商电池页，这类设备只能走蓝牙通道——不是代码能补的。
