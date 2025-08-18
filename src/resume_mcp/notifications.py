"""
System notification functions for cross-platform notifications.
"""
import logging
from typing import Optional

log = logging.getLogger("resume-mcp")


def send_system_notification(title: str, message: str, duration: int = 5000) -> bool:
    """Send a system notification across platforms."""
    try:
        import platform
        system = platform.system().lower()
        
        if system == 'windows':
            try:
                # Try win10toast first
                from win10toast import ToastNotifier
                toaster = ToastNotifier()
                toaster.show_toast(title, message, duration=duration//1000, threaded=True)
                return True
            except ImportError:
                # Fallback to Windows native
                import subprocess
                subprocess.run([
                    'powershell', '-Command',
                    f'[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; $template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02); $template.GetElementsByTagName("text")[0].AppendChild($template.CreateTextNode("{title}")); $template.GetElementsByTagName("text")[1].AppendChild($template.CreateTextNode("{message}")); $toast = [Windows.UI.Notifications.ToastNotification]::new($template); [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier("Claude Resume MCP").Show($toast)'
                ], capture_output=True, timeout=5)
                return True
                
        elif system == 'darwin':  # macOS
            import subprocess
            script = f'''display notification "{message}" with title "{title}"'''
            subprocess.run(['osascript', '-e', script], capture_output=True, timeout=5)
            return True
            
        else:  # Linux
            import subprocess
            subprocess.run(['notify-send', title, message], capture_output=True, timeout=5)
            return True
            
    except Exception as e:
        log.warning(f"Failed to send notification: {e}")
        return False