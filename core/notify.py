"""Windows 通知：低电量预警走系统 Toast，失败则退化为提示音。"""
from __future__ import annotations

import html

from . import winps

_TOAST = r"""
$ErrorActionPreference = 'Stop'
try {
  [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType=WindowsRuntime] | Out-Null
  [Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType=WindowsRuntime] | Out-Null
  $xml = @"
<toast scenario="reminder"><visual><binding template="ToastGeneric"><text>__TITLE__</text><text>__MSG__</text></binding></visual><audio src="ms-winsoundevent:Notification.Reminder"/></toast>
"@
  $doc = New-Object Windows.Data.Xml.Dom.XmlDocument
  $doc.LoadXml($xml)
  $toast = New-Object Windows.UI.Notifications.ToastNotification $doc
  [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('BatteryPulse').Show($toast)
  Write-Output 'OK'
} catch {
  Write-Output ('ERR: ' + $_.Exception.Message)
  exit 1
}
"""


def build_script(title: str, message: str) -> str:
    # 不要用 str.format：PowerShell 的 { } 会被当成格式字段
    return _TOAST.replace("__TITLE__", html.escape(title)).replace("__MSG__", html.escape(message))


def toast(title: str, message: str, sound: bool = True) -> bool:
    try:
        winps.spawn_ps(build_script(title, message))
        return True
    except Exception:
        if sound:
            beep()
        return False


def beep() -> None:
    try:
        import winsound

        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        pass
