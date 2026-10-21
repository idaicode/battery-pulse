"""Claude 风格的托盘弹层菜单。

为什么不用原生 TrackPopupMenu：Windows 菜单的配色、圆角、字体全部不可定制，
只会是一块灰色方角面板。这里改用「分层窗口 + Pillow 绘制」：

- WS_EX_LAYERED + UpdateLayeredWindow，支持逐像素透明，能做圆角和投影；
- 背景层用 3 倍超采样再缩小，圆角边缘平滑；文字在目标分辨率直接绘制，保证清晰；
- 弹出时只是 UpdateLayeredWindow 贴一张位图，延迟在 10ms 量级；
- 没有任何额外进程 / WebView，内存增量为一张位图。

交互：SetCapture 捕获鼠标，点击外部即关闭；ESC 关闭；点击某项回调后关闭，
阈值与开关属于"就地生效"，执行后原地重绘而不关闭。
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# ---------------- 配色（与面板同一套） ----------------
C_BG = (251, 249, 244, 255)        # 卡片米白
C_LINE = (232, 226, 213, 255)      # 分隔线
C_HOVER = (243, 238, 227, 255)     # 悬停底
C_INK = (47, 46, 41, 255)          # 主文字
C_INK2 = (122, 118, 106, 255)      # 次文字
C_INK3 = (160, 155, 143, 255)      # 弱文字
C_ACCENT = (191, 90, 60, 255)      # 陶土色
C_ACCENT_SOFT = (246, 230, 222, 255)
C_GOOD = (78, 107, 87, 255)
C_WARN = (192, 134, 54, 255)
C_BAD = (180, 69, 58, 255)
C_MUTE = (150, 147, 137, 255)
C_TRACK_OFF = (216, 210, 198, 255)

LEVEL_COLORS = {0: C_GOOD, 1: C_WARN, 2: C_BAD, 3: C_MUTE}

# ---------------- Win32 ----------------
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WS_POPUP = 0x80000000
WS_EX_LAYERED = 0x00080000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TOPMOST = 0x00000008

ULW_ALPHA = 0x00000002
AC_SRC_OVER = 0x00
AC_SRC_ALPHA = 0x01

WM_DESTROY = 0x0002
WM_PAINT = 0x000F
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_KEYDOWN = 0x0100
WM_ACTIVATE = 0x0006
WM_MOUSEACTIVATE = 0x0021
MA_NOACTIVATE = 3
VK_ESCAPE = 0x1B

SM_CXSCREEN, SM_CYSCREEN = 0, 1


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]


class BLENDFUNCTION(ctypes.Structure):
    _fields_ = [
        ("BlendOp", ctypes.c_ubyte),
        ("BlendFlags", ctypes.c_ubyte),
        ("SourceConstantAlpha", ctypes.c_ubyte),
        ("AlphaFormat", ctypes.c_ubyte),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

kernel32.GetModuleHandleW.restype = wintypes.HMODULE
user32.CreateWindowExW.restype = wintypes.HWND
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, ctypes.c_void_p,
]
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = ctypes.c_ssize_t
user32.RegisterClassExW.argtypes = [ctypes.c_void_p]
user32.UpdateLayeredWindow.argtypes = [
    wintypes.HWND, wintypes.HDC, ctypes.POINTER(POINT), ctypes.POINTER(SIZE),
    wintypes.HDC, ctypes.POINTER(POINT), wintypes.DWORD, ctypes.POINTER(BLENDFUNCTION), wintypes.DWORD,
]
user32.UpdateLayeredWindow.restype = wintypes.BOOL
user32.SetCapture.argtypes = [wintypes.HWND]
user32.ReleaseCapture.argtypes = []
user32.DestroyWindow.argtypes = [wintypes.HWND]
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.restype = ctypes.c_ssize_t
user32.GetSystemMetrics.argtypes = [ctypes.c_int]
user32.GetSystemMetrics.restype = ctypes.c_int
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetFocus.argtypes = [wintypes.HWND]
user32.PostQuitMessage.argtypes = [ctypes.c_int]
gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.CreateDIBSection.argtypes = [
    wintypes.HDC, ctypes.POINTER(BITMAPINFO), wintypes.UINT,
    ctypes.POINTER(ctypes.c_void_p), wintypes.HANDLE, wintypes.DWORD,
]
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteDC.argtypes = [wintypes.HDC]


# ---------------- 尺寸 ----------------
W_CARD = 296
PAD = 12          # 卡片左右内边距
ROW_H = 32
H_HEADER = 58
SHADOW = 22       # 投影留白

# 行 key
R_OPEN = "open"
R_REFRESH = "refresh"
R_TH_DOWN = "th_down"
R_TH_UP = "th_up"
R_NOTIFY = "notify"
R_SOUND = "sound"
R_LOWPOWER = "low_power"
R_AUTOSTART = "autostart"
R_QUIT = "quit"

THRESHOLDS = (10, 15, 20, 25, 30, 40, 50)


def _font(size: int, bold: bool = False):
    path = "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", size)


def _premultiply(im: Image.Image) -> bytes:
    """UpdateLayeredWindow 要求预乘 alpha，否则半透明边缘会发白。"""
    r, g, b, a = im.split()
    a3 = Image.merge("RGB", (a, a, a))
    rgb = ImageChops.multiply(Image.merge("RGB", (r, g, b)), a3)
    return Image.merge("RGBA", (*rgb.split(), a)).tobytes("raw", "BGRA")


def _ellipsis(d: ImageDraw.ImageDraw, text: str, font, max_w: float) -> str:
    """按像素宽度截断，超长补省略号。"""
    if max_w <= 0 or d.textlength(text, font=font) <= max_w:
        return text
    ell = "…"
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if d.textlength(text[:mid] + ell, font=font) <= max_w:
            lo = mid
        else:
            hi = mid - 1
    return (text[:lo] + ell) if lo else ell


def _round(img: Image.Image, box, radius: int, fill, ss: int = 3) -> None:
    """超采样画圆角矩形再缩小贴回，边缘才干净。"""
    x0, y0, x1, y1 = box
    w, h = int(x1 - x0), int(y1 - y0)
    if w <= 0 or h <= 0:
        return
    layer = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=radius * ss, fill=fill)
    layer = layer.resize((w, h), Image.LANCZOS)
    img.alpha_composite(layer, (int(x0), int(y0)))


class MenuRow:
    __slots__ = ("key", "rect", "kind", "label", "value", "enabled")

    def __init__(self, key, kind, label, value=None, enabled=True):
        self.key = key
        self.kind = kind  # item / toggle / stepper / quit / section
        self.label = label
        self.value = value
        self.enabled = enabled
        self.rect = (0, 0, 0, 0)


class PopupMenu:
    """渲染 + 模态交互。show() 返回 (动作 key, 值) 或 None。"""

    _class_atom = None
    _active: PopupMenu | None = None
    _wndproc_ref = None

    def __init__(self, state: dict, scale: float = 1.0):
        self.s = state
        self.scale = max(1.0, float(scale))
        self.rows: list[MenuRow] = []
        self.hover: str | None = None
        self.done = False
        self.result: tuple | None = None
        self._hwnd = None
        self._img: Image.Image | None = None
        self._layout()

    # ---------- 布局 ----------
    def _layout(self) -> None:
        s = self.scale
        dev = self.s.get("device") or {}
        rows = self.rows
        rows.append(MenuRow("head", "head", dev.get("name") or "未连接设备"))

        y = PAD + H_HEADER + 1 + 8
        rows.append(MenuRow(R_OPEN, "item", "打开面板"))
        rows[-1].rect = (PAD, y, W_CARD - PAD, y + ROW_H)
        y += ROW_H

        rows.append(MenuRow(R_REFRESH, "item", "立即刷新"))
        rows[-1].rect = (PAD, y, W_CARD - PAD, y + ROW_H)
        y += ROW_H
        y += 8

        rows.append(MenuRow("sec_th", "section", "预警阈值"))
        rows[-1].rect = (PAD + 2, y, W_CARD - PAD, y + 22)
        y += 22

        # 阈值控件作为一组居中：[-] 20% [+]
        grp_w = 116
        gx = (W_CARD - grp_w) // 2
        rows.append(MenuRow(R_TH_DOWN, "stepper", "-"))
        rows[-1].rect = (gx, y, gx + 32, y + ROW_H)
        rows.append(MenuRow(R_TH_UP, "stepper", "+"))
        rows[-1].rect = (gx + grp_w - 32, y, gx + grp_w, y + ROW_H)
        rows.append(MenuRow("th_value", "value", f"{self.s.get('warn_threshold', 20)}%"))
        rows[-1].rect = (gx + 32, y, gx + grp_w - 32, y + ROW_H)
        y += ROW_H + 8

        for key, label in (
            (R_NOTIFY, "系统通知"),
            (R_SOUND, "提示音"),
            (R_LOWPOWER, "低功耗模式"),
            (R_AUTOSTART, "开机自启"),
        ):
            rows.append(MenuRow(key, "toggle", label, bool(self.s.get(key))))
            rows[-1].rect = (PAD, y, W_CARD - PAD, y + ROW_H)
            y += ROW_H

        y += 8
        rows.append(MenuRow("divider", "divider", ""))
        rows[-1].rect = (PAD, y, W_CARD - PAD, y + 1)
        y += 8
        rows.append(MenuRow(R_QUIT, "quit", "退出托盘程序"))
        rows[-1].rect = (PAD, y, W_CARD - PAD, y + ROW_H)
        y += ROW_H + PAD + 4

        self.h_logical = y
        self.w_logical = W_CARD + 2  # 卡片外沿
        self.w_px = int(round((self.w_logical + SHADOW * 2) * s))
        self.h_px = int(round((self.h_logical + SHADOW * 2) * s))

    # ---------- 绘制 ----------
    def render(self) -> Image.Image:
        s = self.scale
        img = Image.new("RGBA", (self.w_px, self.h_px), (0, 0, 0, 0))
        ox, oy = SHADOW, SHADOW

        # 投影
        sh = Image.new("RGBA", (self.w_px, self.h_px), (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle(
            (ox * s + 1 * s, oy * s + 5 * s, (ox + self.w_logical) * s - 1 * s, (oy + self.h_logical) * s + 4 * s),
            radius=13 * s, fill=(60, 52, 40, 54),
        )
        sh = sh.filter(ImageFilter.GaussianBlur(7 * s))
        img.alpha_composite(sh)

        # 卡片
        _round(img, (ox * s, oy * s, (ox + self.w_logical) * s, (oy + self.h_logical) * s),
               13, C_BG, ss=4)
        # 1px 描边
        border = Image.new("RGBA", (self.w_px, self.h_px), (0, 0, 0, 0))
        ImageDraw.Draw(border).rounded_rectangle(
            (ox * s, oy * s, (ox + self.w_logical) * s - 1, (oy + self.h_logical) * s - 1),
            radius=13 * s, outline=(226, 219, 204, 255), width=max(1, int(s)),
        )
        img.alpha_composite(border)

        d = ImageDraw.Draw(img)

        def T(x, y, text, size, color=C_INK, bold=False, anchor="la"):
            d.text((ox * s + x * s, oy * s + y * s), text, font=_font(int(size * s), bold),
                   fill=color, anchor=anchor)

        # 悬停高亮（先画，压在文字下）
        for row in self.rows:
            if row.key == self.hover and row.kind in ("item", "toggle", "quit", "stepper"):
                x0, y0, x1, y1 = row.rect
                inset = 6 if row.kind == "stepper" else 0
                _round(img, ((ox + x0 + inset) * s, (oy + y0 + 1) * s,
                             (ox + x1 - inset) * s, (oy + y1 - 1) * s), 8, C_HOVER, ss=4)

        # ---- 头部 ----
        dev = self.s.get("device") or {}
        pct = dev.get("percent")
        level = dev.get("level", 3)
        accent = LEVEL_COLORS[level]
        name = dev.get("name") or "未连接设备"
        # 名字要给右侧数字让位，超长就截断（否则会压在百分比上）
        name_font = _font(int(14.5 * s), True)
        max_name_w = (self.w_logical - PAD * 2 - 78) * s
        name = _ellipsis(d, name, name_font, max_name_w)
        T(PAD + 2, PAD + 9, name, 14.5, C_INK, True)

        # 状态点 + 状态行
        sub = dev.get("status_line") or "—"
        sub_font = _font(int(11.5 * s))
        sub = _ellipsis(d, sub, sub_font, (self.w_logical - PAD * 2 - 8) * s)
        dot_y = PAD + 36
        _round(img, ((ox + PAD + 3) * s, (oy + dot_y + 5) * s, (ox + PAD + 8) * s, (oy + dot_y + 10) * s),
               3, accent, ss=4)
        T(PAD + 14, dot_y, sub, 11.5, C_INK2)

        # 右侧数字
        if pct is None:
            T(self.w_logical - PAD - 5, PAD + 10, "—", 26, C_INK3, True, "ra")
        else:
            T(self.w_logical - PAD - 13, PAD + 10, str(int(pct)), 27, accent, True, "ra")
            d.text((ox * s + (self.w_logical - PAD - 10) * s, oy * s + (PAD + 27) * s), "%",
                   font=_font(int(11 * s)), fill=C_INK3, anchor="ls")

        # 头部分隔线
        d.line((ox * s + (PAD + 2) * s, oy * s + (PAD + H_HEADER) * s,
                ox * s + (self.w_logical - PAD - 2) * s, oy * s + (PAD + H_HEADER) * s),
               fill=C_LINE, width=max(1, int(s)))

        # ---- 行 ----
        for row in self.rows:
            x0, y0, x1, y1 = row.rect
            cy = (y0 + y1) / 2
            if row.kind == "item":
                T(PAD + 12, cy, row.label, 13, C_INK, False, "lm")
            elif row.kind == "section":
                T(PAD + 2, cy, row.label, 10.5, (138, 132, 118, 255), False, "lm")
            elif row.kind == "stepper":
                # 小方块按钮 + 图形符号（不用字形，避免字体缺字渲染成豆腐块）
                bx0, by0, bx1, by1 = x0 + 6, y0 + 4, x1 - 6, y1 - 4
                _round(img, ((ox + bx0) * s, (oy + by0) * s, (ox + bx1) * s, (oy + by1) * s),
                       7, (236, 229, 214, 255), ss=4)
                cx = x0 + (x1 - x0) / 2
                cy2 = y0 + (y1 - y0) / 2
                lw = max(1, int(round(1.7 * s)))
                arm = 4.2
                d.line((ox * s + (cx - arm) * s, oy * s + cy2 * s,
                        ox * s + (cx + arm) * s, oy * s + cy2 * s), fill=C_INK, width=lw)
                if row.key == R_TH_UP:
                    d.line((ox * s + cx * s, oy * s + (cy2 - arm) * s,
                            ox * s + cx * s, oy * s + (cy2 + arm) * s), fill=C_INK, width=lw)
            elif row.kind == "value":
                T((x0 + x1) / 2, cy, row.label, 13, C_INK, True, "mm")
            elif row.kind == "toggle":
                T(PAD + 12, cy, row.label, 13, C_INK, False, "lm")
                self._switch(img, x1 - 12 - 34, cy - 9.5, bool(row.value))
            elif row.kind == "divider":
                d.line((ox * s + x0 * s, oy * s + y0 * s, ox * s + x1 * s, oy * s + y0 * s),
                       fill=C_LINE, width=max(1, int(s)))
            elif row.kind == "quit":
                T(PAD + 12, cy, row.label, 13, C_ACCENT, False, "lm")
        return img

    def _switch(self, img: Image.Image, x: float, y: float, on: bool) -> None:
        s = self.scale
        ox, oy = SHADOW, SHADOW
        w, h = 34, 19
        track = C_ACCENT if on else C_TRACK_OFF
        _round(img, ((ox + x) * s, (oy + y) * s, (ox + x + w) * s, (oy + y + h) * s), 9.5, track, ss=4)
        kx = x + (w - 15 - 2) if on else x + 2
        _round(img, ((ox + kx) * s, (oy + y + 2) * s, (ox + kx + 15) * s, (oy + y + 2 + 15) * s),
               7.5, (255, 255, 255, 255), ss=4)

    # ---------- 命中 ----------
    def _hit(self, px: float, py: float) -> MenuRow | None:
        s = self.scale
        lx = px / s - SHADOW
        ly = py / s - SHADOW
        for row in self.rows:
            x0, y0, x1, y1 = row.rect
            if x0 <= lx <= x1 and y0 <= ly <= y1:
                return row
        return None

    # ---------- 窗口 ----------
    def _ensure_class(self) -> None:
        if PopupMenu._class_atom:
            return
        hinst = kernel32.GetModuleHandleW(None)
        PopupMenu._wndproc_ref = WNDPROC(_global_wndproc)

        class WNDCLASSEXW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.UINT), ("style", wintypes.UINT), ("lpfnWndProc", ctypes.c_void_p),
                ("cbClsExtra", ctypes.c_int), ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON), ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR),
                ("hIconSm", wintypes.HICON),
            ]

        wc = WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
        wc.lpfnWndProc = ctypes.cast(PopupMenu._wndproc_ref, ctypes.c_void_p)
        wc.hInstance = hinst
        wc.lpszClassName = "BatteryPulseMenu"
        user32.RegisterClassExW(ctypes.byref(wc))
        PopupMenu._class_atom = 1

    def _blit(self) -> None:
        self._img = self.render()
        hwnd = self._hwnd
        hdc_screen = user32.GetDC(None)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        bi = BITMAPINFO()
        bi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bi.bmiHeader.biWidth = self.w_px
        bi.bmiHeader.biHeight = -self.h_px
        bi.bmiHeader.biPlanes = 1
        bi.bmiHeader.biBitCount = 32
        bits = ctypes.c_void_p()
        hbm = gdi32.CreateDIBSection(hdc_screen, ctypes.byref(bi), 0, ctypes.byref(bits), None, 0)
        old = gdi32.SelectObject(hdc_mem, hbm)
        raw = _premultiply(self._img)
        ctypes.memmove(bits, raw, len(raw))

        pt_dst = POINT(self._x, self._y)
        size = SIZE(self.w_px, self.h_px)
        pt_src = POINT(0, 0)
        bf = BLENDFUNCTION(AC_SRC_OVER, 0, 255, AC_SRC_ALPHA)
        user32.UpdateLayeredWindow(hwnd, hdc_screen, ctypes.byref(pt_dst), ctypes.byref(size),
                                   hdc_mem, ctypes.byref(pt_src), 0, ctypes.byref(bf), ULW_ALPHA)
        gdi32.SelectObject(hdc_mem, old)
        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_screen)

    def show(self, x: int, y: int) -> tuple[str, object] | None:
        """在 (x, y) 弹开（右下角对齐该点）。返回 (动作, 值)。"""
        # 同时只允许一个菜单：多开会互相抢 _active，先弹的那个就再也没人关得掉
        prev = PopupMenu._active
        if prev is not None and prev is not self:
            prev.close()

        self._ensure_class()
        sw, sh = user32.GetSystemMetrics(SM_CXSCREEN), user32.GetSystemMetrics(SM_CYSCREEN)
        self._x = max(4, min(int(x) - self.w_px + int(SHADOW * self.scale), sw - self.w_px - 4))
        self._y = max(4, min(int(y) - self.h_px + int(SHADOW * self.scale), sh - self.h_px - 4))

        hinst = kernel32.GetModuleHandleW(None)
        PopupMenu._active = self
        self._hwnd = user32.CreateWindowExW(
            WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_TOPMOST, "BatteryPulseMenu", "", WS_POPUP,
            self._x, self._y, self.w_px, self.h_px, None, None, hinst, None,
        )
        if not self._hwnd:
            PopupMenu._active = None
            return None
        self._blit()
        user32.ShowWindow(self._hwnd, 5)  # SW_SHOW
        user32.SetForegroundWindow(self._hwnd)
        user32.SetFocus(self._hwnd)
        user32.SetCapture(self._hwnd)

        msg = wintypes.MSG()
        while not self.done:
            ret = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if ret <= 0:
                break
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        self.close()
        return self.result

    def close(self) -> None:
        if not self.done:
            self.done = True
        if self._hwnd:
            user32.ReleaseCapture()
            user32.DestroyWindow(self._hwnd)
            self._hwnd = None
        if PopupMenu._active is self:
            PopupMenu._active = None

    # ---------- 交互 ----------
    def on_message(self, hwnd, msg, wparam, lparam):
        if msg == WM_MOUSEMOVE:
            row = self._hit(lparam & 0xFFFF, (lparam >> 16) & 0xFFFF)
            key = row.key if row and row.kind in ("item", "toggle", "quit", "stepper") else None
            if key != self.hover:
                self.hover = key
                self._blit()
            return 0
        if msg == WM_LBUTTONDOWN:
            row = self._hit(lparam & 0xFFFF, (lparam >> 16) & 0xFFFF)
            if not row:
                self.close()
                return 0
            if row.kind == "stepper":
                self.result = (row.key, None)
                self.done = True
                return 0
            if row.kind in ("item", "toggle", "quit"):
                self.result = (row.key, row.value)
                self.done = True
                return 0
            return 0
        if msg == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE
        if msg == WM_KEYDOWN and (wparam & 0xFFFF) == VK_ESCAPE:
            self.close()
            return 0
        if msg == WM_DESTROY:
            # 这里绝对不能 PostQuitMessage：菜单窗口运行在托盘线程上，
            # 投 WM_QUIT 会把托盘的整个消息循环一起结束掉。
            self.done = True
            return 0
        if msg in (WM_PAINT,):
            return 0
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)


def _global_wndproc(hwnd, msg, wparam, lparam):
    inst = PopupMenu._active
    if inst is not None:
        try:
            return inst.on_message(hwnd, msg, wparam, lparam)
        except Exception:
            pass
    return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
