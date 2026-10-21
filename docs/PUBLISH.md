# 从本地文件到 GitHub 仓库：完整流程

这份文档假设你**没做过开源发布**，从"一堆能跑的代码"讲到"别人 clone 下来就能跑、能下载 exe"。
每一步都给了可直接复制的命令。

> 全文用 `idaicode`（本项目的 GitHub 账号）和 `battery-pulse`（仓库名）举例。
> 换成你自己的：GitHub 右上角头像就是用户名；仓库名建议就用 `battery-pulse`（小写 + 连字符，是 GitHub 的通行写法）。

---

## 0. 先搞清楚：一个"完整项目"到底有哪些东西

代码只是其中一层。别人（包括三个月后的你）判断一个项目靠不靠谱，看的是这五层：

| 层 | 内容 | 缺了会怎样 |
|---|---|---|
| **代码** | `app.py`、`core/`、`ui/` | —— |
| **工程** | `.gitignore`、`requirements.txt`、`pyproject.toml`、`.editorconfig` | 把 65 MB 的 `.venv` 传上去；换台机器装不起来 |
| **文档** | `README.md`、`CHANGELOG.md`、`LICENSE`、`CONTRIBUTING.md` | 别人不知道这是什么、能不能商用、怎么参与 |
| **协作** | `.github/ISSUE_TEMPLATE/`、`PULL_REQUEST_TEMPLATE.md`、Actions | 收到的 issue 全是"用不了，怎么办" |
| **发布** | `release.bat`、`v1.0.0` tag、Release 附件、Actions 自动打包 | 不会 Python 的用户拿不到能直接双击的东西 |

**最重要的一条：`.gitignore` 必须在第一次 `git add` 之前就写好。**
一旦把 `.venv` 或 `dist` 提交进去，它们会永久留在 git 历史里——后面再删文件也没用，得重写历史（`git filter-repo`）才能瘦下来。

---

## 1. 本地整理（这次的改动已全部做完）

### 1.1 已经生成的文件

```
battery-pulse/
├─ .gitignore                     ← 排除 venv / build / dist / data / 缓存
├─ .editorconfig                  ← 统一缩进与换行（bat 用 CRLF，其余 LF）
├─ LICENSE                        ← MIT，可自由使用/修改/商用
├─ README.md                      ← 项目主页，GitHub 上渲染的就是它
├─ CHANGELOG.md                   ← 每个版本改了什么
├─ CONTRIBUTING.md                ← 怎么搭环境、怎么提交
├─ pyproject.toml                 ← 项目元数据 + ruff 规则 + 版本号
├─ requirements.txt               ← 运行依赖
├─ requirements-dev.txt           ← 开发依赖（pyinstaller / ruff / pytest）
├─ release.bat                    ← 打包 + 压成可上传的 zip
├─ docs/PUBLISH.md                ← 本文件
├─ .github/
│  ├─ workflows/build.yml         ← CI：每次 push 自动打包，打 tag 自动发 Release
│  ├─ ISSUE_TEMPLATE/*.yml        ← 提单时自动带表单
│  └─ PULL_REQUEST_TEMPLATE.md
└─ .vscode/                       ← 解释器路径、推荐插件、F5 调试配置
```

### 1.2 绝对不能进仓库的三样东西

| 目录 | 大小 | 为什么不能传 |
|---|---|---|
| `.venv/` | 65 MB | 本机绝对路径写死在里面，别人 clone 下来是坏的；依赖用 `requirements.txt` 描述 |
| `build/` `dist/` | 21 + 114 MB | 构建产物，且单个文件超 GitHub 的 100 MB 硬限制会直接拒收 |
| `data/` | 67 MB | 有 `config.json`（**含你的键盘 MAC 地址**）、日志、WebView2 缓存 |

这些已经写在 `.gitignore` 里了。`data/config.json` 在程序首次运行时自动生成，开源仓库里不需要它。

### 1.3 验证一下忽略规则是否真的生效

```bat
cd /d "D:\appdata\Workbuddy Files\2026-10-19-06-23-05\battery-monitor"
git init
git status --short
```

输出里**不应该出现** `.venv/`、`dist/`、`build/`、`data/` 中的任何一行。
如果出现了，说明 `.gitignore` 没被读到（检查文件名前面有没有点、编码是不是 UTF-8 无 BOM）。

---

## 2. 用 VS Code 打开并跑起来

1. VS Code → `文件` → `打开文件夹` → 选 `battery-monitor`（注意：选**这一层**，不要选它的父目录）
2. 右下角/命令面板 `Ctrl+Shift+P` → `Python: Select Interpreter` → 选 `.venv\Scripts\python.exe`
   - 仓库自带的 `.vscode/settings.json` 已经指好这个路径，通常会自动选中
3. 首次拉下来的机器没有 `.venv`，先建一个：

```bat
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

4. 按 `F5` → 选「面板 + 托盘」，直接带断点调试。三个预设配置都能用：
   - 面板 + 托盘
   - 只起托盘（改图标/菜单时用，省内存）
   - 只起服务（浏览器开 `127.0.0.1:8731` 调界面，改 html 刷新即可）

> `.gitignore` 里已经放行了 `.vscode/settings.json`、`extensions.json`、`launch.json`，只忽略个人化的其它文件。这样别人 clone 下来就有同样的调试配置，这是加分项。

---

## 3. 本地提交（git 的三个概念）

先理解三个词，后面所有命令都绕不开：

- **工作区**：你磁盘上的文件，改了就是改了
- **暂存区（index）**：`git add` 把改动放进待提交清单
- **提交（commit）**：`git commit` 把暂存区拍一张快照，永久记录，带作者和时间

```bat
cd /d "D:\appdata\Workbuddy Files\2026-10-19-06-23-05\battery-monitor"

:: 1) 初始化仓库（只做一次，生成 .git 目录）
git init

:: 2) 把默认分支改名为 main（GitHub 现在的默认叫法）
git branch -M main

:: 3) 暂存全部改动，并确认到底会提交哪些文件
git add -A
git status --short

:: 4) 提交
git commit -m "feat: Battery Pulse 1.0.0 首个版本"

:: 5) 确认提交成功
git log --oneline
```

`git status --short` 的读法：`A` 是新增，`M` 是修改，`??` 是未跟踪。
这时候应该看到 40 个左右的 `A`，全部是源码、文档、截图、配置——**没有** `.venv`、`dist`、`data`。

### 提交信息怎么写

推荐 Conventional Commits，一眼看出改动性质，后面做 CHANGELOG 也方便：

```
feat:     新功能        feat(hidpp): 支持 feature 0x1004
fix:      修 bug        fix(tray): NIM_ADD 失败后重试
docs:     文档          docs: 补充 2.4G 模式限制
refactor: 重构          refactor(menu): 拆出绘制与命中测试
chore:    杂活          chore: 升级 pyinstaller
```

---

## 4. 在 GitHub 建一个空仓库

1. 打开 https://github.com/new
2. **Repository name** 填 `battery-pulse`
3. **Description** 填：`读取罗技 HID++ / 蓝牙 GATT 外设真实电量的 Windows 托盘工具`
4. 选 **Public**（要私有也行，但 Release 下载页对外不可见）
5. **下面三个复选框全部不要勾**：Add a README / Add .gitignore / Choose a license
   —— 本地已经有了，勾了会在远端先产生一个 commit，push 时就得先 `pull --rebase`，新手最容易卡在这
6. `Create repository`

建完页面会显示一串命令，先别急着复制，看下一节选认证方式。

---

## 5. 认证：GitHub 早就不认密码了

`git push` 时如果弹窗让你输密码，输账号密码一定失败（2021 年起已废弃）。两条路选一条：

### 方案 A：HTTPS + Personal Access Token（推荐，5 分钟）

1. 打开 https://github.com/settings/tokens → `Generate new token` → **Tokens (classic)**
2. Note 填 `battery-pulse-push`，Expiration 选 90 天
3. 勾选 **`repo`** 这一整个大项（它包含读写仓库、管理 Release）
4. `Generate token` → **立刻复制**（`ghp_` 开头，页面关掉就再也看不到了）
5. 回到终端：

```bat
git remote add origin https://github.com/idaicode/battery-pulse.git
git push -u origin main
```

弹窗里：
- 用户名：`idaicode`
- 密码：**粘贴那串 token**（不是账号密码）

Windows 会用「凭据管理器」记住它，以后 push 不用再输。
token 泄露了就在同一页面 Revoke 掉，重新生成一个。

```bat
:: 想清掉已保存的凭据（换账号/换 token 时）
cmdkey /delete:git:https://github.com
```

### 方案 B：SSH 密钥（一次配置，长期免密）

```bat
:: 1) 生成密钥（一路回车，密码可留空）
ssh-keygen -t ed25519 -C "642522946@qq.com"

:: 2) 复制公钥到剪贴板
clip < %USERPROFILE%\.ssh\id_ed25519.pub
```

3. 打开 https://github.com/settings/keys → `New SSH key` → Title 随便填，Key 粘贴 → `Add SSH key`
4. 验证并推送：

```bat
ssh -T git@github.com
:: 看到 "Hi idaicode! You've successfully authenticated" 就成了

git remote add origin git@github.com:idaicode/battery-pulse.git
git push -u origin main
```

> 注意 `%USERPROFILE%` 在 Git Bash 里要写成 `~/.ssh/id_ed25519.pub`。

`-u` 的作用是把本地 `main` 和远端 `origin/main` 绑定，之后直接 `git push` 就行。

---

## 6. 推送成功后该看到什么

刷新 `https://github.com/idaicode/battery-pulse`：

- 首页自动渲染 `README.md`（截图能显示，因为 `shots/` 已经一起提交了）
- 右上角显示 **MIT license**
- 文件列表里只有 6 个目录 + 十几个文件，**没有** `.venv` / `dist`
- `Actions` 标签页里 `build` 已经在跑（`build.yml` 触发），第一次约 3–5 分钟

如果 Actions 里失败，点进去看日志。最常见的是 `ruff` 报错——这一步设了 `continue-on-error`，不会阻断构建；真阻断的通常是 `PyInstaller` 找不到某个 hiddenimport。

---

## 7. 打包并发布第一个版本

### 7.1 本地打包

```bat
release.bat
```

它做的事：

1. 从 `core/__init__.py` 读 `__version__`（版本号只有一个来源，不会写错）
2. 跑 `PyInstaller --clean battery-monitor.spec`
3. 把 `dist\BatteryPulse\*` 压成 `release\BatteryPulse-v1.0.0-win64.zip`

产物约 40–55 MB。直接传 zip，不要把 `dist/BatteryPulse/` 目录里的几千个文件一个个传。

### 7.2 打 tag

tag 是给某个 commit 起的"版本别名"，Release 就挂在 tag 上：

```bat
git tag -a v1.0.0 -m "Battery Pulse 1.0.0"
git push origin v1.0.0
```

> 推送 tag 会触发 `build.yml` 里的「发布 Release」步骤（`if: startsWith(github.ref, 'refs/tags/v')`），
> CI 会自己打包并生成 Release。**如果你用了这条路径，就不需要手动上传 zip 了**，等 5 分钟去 Releases 看即可。

### 7.3 手动发 Release（不上 CI 也能做）

1. 仓库页右侧 `Releases` → `Draft a new release`
2. `Choose a tag` → 选 `v1.0.0`（或新建）
3. Title：`Battery Pulse 1.0.0`
4. 描述直接抄 `CHANGELOG.md` 的 1.0.0 段落
5. 把 `release\BatteryPulse-v1.0.0-win64.zip` 拖进附件区（单文件上限 2 GB）
6. `Publish release`

发完后得到形如 `https://github.com/idaicode/battery-pulse/releases/latest` 的固定链接，可以放进 README 的下载按钮——以后发新版，这个链接永远指向最新版。

---

## 8. 后续日常：改完代码怎么更新

```bat
git status                     :: 看改了啥
git add -A
git commit -m "fix(tray): 修正 150% 缩放下的点击偏移"
git push
```

发新版时改三处，再走一遍 tag + Release：

1. `core/__init__.py` 里的 `__version__`
2. `pyproject.toml` 里的 `version`
3. `CHANGELOG.md` 顶部加一段

```bat
git commit -am "chore: 发布 1.0.1"
git tag -a v1.0.1 -m "Battery Pulse 1.0.1"
git push && git push origin v1.0.1
```

### 分支策略（一个人开发够用）

| 场景 | 做法 |
|---|---|
| 小改动 | 直接在 `main` 上改，提交，push |
| 大改动 / 试验 | `git checkout -b feat/xxx`，做完 `git push -u origin feat/xxx`，在网页上开 PR 合并 |
| 改坏了想回退 | `git log --oneline` 找到好的 commit，`git revert <hash>` |

---

## 9. 让 README 更"像个项目"

已经做了的：预览图、托盘菜单示意、原理拆解、性能数据、排错表——这些比徽章值钱得多。

可以再加的（都在 README 顶部）：

```markdown
[![build](https://github.com/idaicode/battery-pulse/actions/workflows/build.yml/badge.svg)](https://github.com/idaicode/battery-pulse/actions/workflows/build.yml)
[![release](https://img.shields.io/github/v/release/idaicode/battery-pulse)](https://github.com/idaicode/battery-pulse/releases/latest)
[![license](https://img.shields.io/github/license/idaicode/battery-pulse)](LICENSE)
```

徽章不是装饰：`build` 徽章是绿的，说明这个项目当前是能构建的；`release` 徽章直接给出下载入口。

---

## 10. 常见问题

| 报错 | 原因 | 解法 |
|---|---|---|
| `remote: Support for password authentication was removed` | 用了账号密码 | 换 PAT 或 SSH（第 5 节） |
| `remote: Repository not found` | 仓库名/用户名拼错，或 token 没勾 `repo` | 重新 `git remote set-url origin <正确地址>` |
| `failed to push some refs ... fetch first` | 远端有本地没有的 commit（建仓时勾了 README） | `git pull --rebase origin main` 再 push |
| `file is 114 MB; this exceeds GitHub's file size limit of 100 MB` | `dist/` 被提交了 | `git rm -r --cached dist` 后再 commit；已进历史的要 `git filter-repo` |
| `LF will be replaced by CRLF` | Windows 换行提示 | 忽略即可；`.editorconfig` 已规定 bat 用 CRLF |
| 中文文件名显示成乱码 | 编码问题 | `git config --global core.quotepath false` |
| push 卡住不动 / `Failed to connect to github.com:443` | 直连被墙，或环境变量里有个不通的代理 | 见下一行 |
| `CONNECT tunnel failed, response 502`<br>`schannel: failed to receive handshake` | 走了一个不支持 github.com 的代理（常见于只放行个别域名的本地代理） | 先探端口：`curl -x http://127.0.0.1:7897 -o NUL -w "%{http_code}" https://github.com` 返回 200 才算能用；然后 `git config --local http.proxy http://127.0.0.1:7897`（`--local` 只影响本仓库，不会进版本库）。注意 **git 配置优先于环境变量**，所以配了 config 就一定走它 |
| Actions 打包出的 exe 起不来 | 缺 WebView2 运行时 | 目标机装 [WebView2 Runtime](https://developer.microsoft.com/microsoft-edge/webview2/)（Win11 自带） |

---

## 11. 一张图记住整个流程

```
本地代码
  │  .gitignore 先写好        ← 决定哪些永远不进仓库
  ├─ git init / add / commit  ← 本地快照
  ├─ GitHub 建空仓库
  ├─ git remote add origin
  ├─ git push -u origin main  ← 代码上线
  ├─ release.bat              ← 打出 zip
  └─ git tag v1.0.0 + push    ← 触发 CI 自动发 Release
```

到这里，这个项目就同时具备了：可读的源码、可复现的环境、可下载的成品、可追踪的变更记录、可协作的入口。

---

## 附录 A：两条路线，你走的是哪条

网上多数教程（包括 CSDN 上那些"VSCode 同步到 GitHub"）走的是 **clone 路线**：

```
GitHub 建仓（可以勾 README）
   └─ VSCode: Ctrl+Shift+P → Git: 克隆 → 填 URL → 选本地文件夹
        └─ 在克隆出来的空目录里新建代码
             └─ 源代码管理 → 提交 → 点「同步更改」
```

本文走的是 **push 路线**：

```
本地已经有能跑的代码
   └─ 写 .gitignore（先在本地挡住 venv/dist/data）
        └─ git init → add → commit
             └─ GitHub 建「空」仓 → remote add → push
```

| | clone 路线 | push 路线（本文） |
|---|---|---|
| 起点 | 远端先有仓库 | 本地先有代码 |
| 适合 | 从零开始的新项目 | **代码已经在本机跑起来了** |
| 已有代码怎么办 | 要手动挪进克隆目录，容易连 `.venv`、`dist` 一起带进去 | 原地 `git init`，什么都不用搬 |
| `.gitignore` | 教程通常不提 | 第一步就配，避免把 65 MB 依赖和本机 MAC 传上去 |
| 版本发布 | 只有代码 | tag + Release 附件 + CI 自动打包 |

**如果你的代码已经在本地跑通了，用 push 路线。** 反过来，如果只是想在 GitHub 上开个新坑写点东西，clone 路线更省事。

## 附录 B：HTTPS + PAT 与 SSH 怎么选

两者只是"证明你是你"的方式不同，传输的内容完全一样，安全性也相当。

| | HTTPS + PAT | SSH |
|---|---|---|
| 原理 | 每次连接带一枚令牌，由系统凭据管理器保存 | 本地生成一对密钥，公钥登记在 GitHub，私钥留本机 |
| 首次配置 | 网页生成 token（`ghp_...`，勾 `repo`），push 时当密码粘贴一次 | `ssh-keygen -t ed25519` → 把 `.pub` 内容贴到 GitHub |
| 之后 | 免密（凭据已记住） | 天生免密 |
| 换机器 | 要重新生成 / 搬 token | 复制 `~/.ssh` 或重新生成 |
| 撤销 | 网页 Revoke，立刻失效 | 删掉那把公钥 |
| 适合 | 新手、偶尔推一次 | 长期开发、多仓库、多机器 |

**Git Bash 不是第三种认证方式**，它是 Windows 上的一个终端程序（Git for Windows 自带），提供 `ls`、`cat`、`ssh-keygen`、`clip` 这些 Linux 风格命令。它和 cmd、PowerShell 是并列关系——决定你"在哪敲命令"；HTTPS/SSH 决定你"怎么证明身份"。这两件事常被教程并列着说，其实是两个维度。

在本项目里：

- `.bat` 是 cmd 脚本，双击运行最省事；在 Git Bash 里要写 `cmd //c start.bat`
- `ssh-keygen`、`clip` 这类命令在 Git Bash 里更顺；PowerShell 里 `clip` 也自带
- VS Code 里换终端：终端面板右上角下拉 → `Select Default Profile` → Git Bash

