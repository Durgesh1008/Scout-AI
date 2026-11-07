import logging
import subprocess
import requests
from app.config import settings

logger = logging.getLogger(__name__)


def send_telegram(message: str) -> dict:
    """Send alert via Telegram Bot."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return {"sent": False, "channel": "telegram", "reason": "Not configured"}

    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": settings.telegram_chat_id,
        "text": message[:4000],
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }

    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        return {"sent": True, "channel": "telegram"}
    except requests.HTTPError:
        # Fallback without markdown if markdown parsing failed
        try:
            payload.pop("parse_mode", None)
            response = requests.post(url, json=payload, timeout=15)
            response.raise_for_status()
            return {"sent": True, "channel": "telegram"}
        except Exception as e:
            logger.error(f"Telegram notification error: {e}")
            return {"sent": False, "channel": "telegram", "error": str(e)}
    except Exception as e:
        logger.error(f"Telegram notification error: {e}")
        return {"sent": False, "channel": "telegram", "error": str(e)}


def send_discord(message: str, title: str = "Scout-AI Morning Briefing") -> dict:
    """Send alert via Discord Webhook with rich embed formatting."""
    if not settings.discord_webhook_url:
        return {"sent": False, "channel": "discord", "reason": "Not configured"}

    payload = {
        "username": "Scout-AI Assistant",
        "avatar_url": "https://img.icons8.com/color/96/bot.png",
        "embeds": [
            {
                "title": title[:256],
                "description": message[:4000],
                "color": 3447003,  # Discord blurple
            }
        ]
    }

    try:
        response = requests.post(settings.discord_webhook_url, json=payload, timeout=15)
        response.raise_for_status()
        return {"sent": True, "channel": "discord"}
    except Exception as e:
        logger.error(f"Discord notification error: {e}")
        return {"sent": False, "channel": "discord", "error": str(e)}


def send_desktop_notification(title: str, message: str) -> dict:
    """Send a Windows desktop toast notification via PowerShell."""
    if not settings.enable_desktop_notifications:
        return {"sent": False, "channel": "desktop", "reason": "Disabled"}

    # Sanitize inputs
    clean_title = title.replace('"', '`"').replace("'", "''")[:60]
    clean_msg = message.replace('"', '`"').replace("'", "''")[:200]

    ps_script = f"""
    [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
    $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
    $textNodes = $template.GetElementsByTagName("text")
    $textNodes.Item(0).AppendChild($template.CreateTextNode("{clean_title}")) > $null
    $textNodes.Item(1).AppendChild($template.CreateTextNode("{clean_msg}")) > $null
    $toast = [Windows.UI.Notifications.ToastNotification]::new($template)
    [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Scout-AI").Show($toast)
    """

    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            timeout=10,
            check=False
        )
        return {"sent": True, "channel": "desktop"}
    except Exception as e:
        logger.debug(f"Desktop notification fallback triggered: {e}")
        return {"sent": False, "channel": "desktop", "error": str(e)}


def notify(message: str, title: str = "Scout-AI Update") -> dict:
    """
    Broadcast message to all configured channels (Telegram, Discord, Desktop).
    """
    results = {}
    results["telegram"] = send_telegram(message)
    results["discord"] = send_discord(message, title)
    results["desktop"] = send_desktop_notification(title, message)
    return results
