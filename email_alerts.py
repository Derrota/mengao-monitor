"""
Mengão Monitor - Email Alert Module
SMTP email notifications for endpoint status changes.
"""

import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional
from dataclasses import dataclass


@dataclass
class EmailConfig:
    """Email configuration."""
    enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    use_tls: bool = True
    username: str = ""
    password: str = ""
    from_addr: str = ""
    to_addrs: list = None
    events: list = None  # ["down", "up", "error"]
    cooldown: int = 300  # seconds between alerts for same endpoint
    
    def __post_init__(self):
        if self.to_addrs is None:
            self.to_addrs = []
        if self.events is None:
            self.events = ["down", "up"]


class EmailAlertSender:
    """Send email alerts for endpoint status changes."""
    
    def __init__(self, config: EmailConfig):
        self.config = config
        self.last_alert: dict = {}  # {endpoint_name: timestamp}
    
    def _should_send(self, endpoint_name: str, event: str) -> bool:
        """Check if alert should be sent based on cooldown and event type."""
        if not self.config.enabled:
            return False
        
        if event not in self.config.events:
            return False
        
        # Check cooldown
        last_time = self.last_alert.get(endpoint_name, 0)
        now = datetime.now().timestamp()
        if now - last_time < self.config.cooldown:
            return False
        
        return True
    
    def _create_html_body(self, result: dict, event: str) -> str:
        """Create HTML email body."""
        name = result.get("name", "Unknown")
        url = result.get("url", "")
        status = result.get("status", "unknown")
        status_code = result.get("status_code", 0)
        response_time = result.get("response_time_ms", 0)
        error = result.get("error", "")
        timestamp = result.get("timestamp", datetime.now().isoformat())
        
        # Colors based on event
        if event == "up":
            color = "#28a745"
            icon = "✅"
            title = "Endpoint Restored"
        elif event == "down":
            color = "#dc3545"
            icon = "❌"
            title = "Endpoint Down"
        else:
            color = "#ffc107"
            icon = "⚠️"
            title = "Endpoint Error"
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ background: {color}; color: white; padding: 20px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 24px; }}
                .content {{ padding: 20px; }}
                .info-row {{ display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #eee; }}
                .info-label {{ color: #666; font-weight: bold; }}
                .info-value {{ color: #333; }}
                .status-badge {{ display: inline-block; padding: 4px 12px; border-radius: 4px; color: white; background: {color}; }}
                .footer {{ background: #1a1a1a; color: #999; padding: 15px; text-align: center; font-size: 12px; }}
                .footer a {{ color: #c8102e; text-decoration: none; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>{icon} {title}</h1>
                    <p>Mengão Monitor Alert</p>
                </div>
                <div class="content">
                    <div class="info-row">
                        <span class="info-label">Endpoint:</span>
                        <span class="info-value">{name}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">URL:</span>
                        <span class="info-value"><a href="{url}">{url}</a></span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Status:</span>
                        <span class="info-value"><span class="status-badge">{status.upper()}</span></span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">HTTP Code:</span>
                        <span class="info-value">{status_code}</span>
                    </div>
                    <div class="info-row">
                        <span class="info-label">Response Time:</span>
                        <span class="info-value">{response_time}ms</span>
                    </div>
                    {f'<div class="info-row"><span class="info-label">Error:</span><span class="info-value" style="color: #dc3545;">{error}</span></div>' if error else ''}
                    <div class="info-row">
                        <span class="info-label">Timestamp:</span>
                        <span class="info-value">{timestamp}</span>
                    </div>
                </div>
                <div class="footer">
                    <p>🦞 Mengão Monitor v1.4 | <a href="https://github.com/Derrota/mengao-monitor">GitHub</a></p>
                    <p>Uma vez Flamengo, sempre Flamengo! 🔴⚫</p>
                </div>
            </div>
        </body>
        </html>
        """
        return html
    
    def _create_plain_body(self, result: dict, event: str) -> str:
        """Create plain text email body."""
        name = result.get("name", "Unknown")
        url = result.get("url", "")
        status = result.get("status", "unknown")
        status_code = result.get("status_code", 0)
        response_time = result.get("response_time_ms", 0)
        error = result.get("error", "")
        timestamp = result.get("timestamp", "")
        
        if event == "up":
            title = "✅ ENDPOINT RESTORED"
        elif event == "down":
            title = "❌ ENDPOINT DOWN"
        else:
            title = "⚠️ ENDPOINT ERROR"
        
        text = f"""
{title}
{'=' * 40}

Endpoint: {name}
URL: {url}
Status: {status.upper()}
HTTP Code: {status_code}
Response Time: {response_time}ms
{f'Error: {error}' if error else ''}
Timestamp: {timestamp}

---
🦞 Mengão Monitor v1.4
Uma vez Flamengo, sempre Flamengo! 🔴⚫
        """
        return text.strip()
    
    def send(self, result: dict, event: str, logger=None) -> bool:
        """
        Send email alert.
        
        Args:
            result: Check result dict
            event: Event type ("up", "down", "error")
            logger: Optional logger instance
            
        Returns:
            True if sent successfully, False otherwise
        """
        endpoint_name = result.get("name", "unknown")
        
        if not self._should_send(endpoint_name, event):
            return False
        
        try:
            # Create message
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"🦞 Mengão Monitor: {result.get('name', 'Unknown')} is {event.upper()}"
            msg["From"] = self.config.from_addr
            msg["To"] = ", ".join(self.config.to_addrs)
            
            # Attach plain text and HTML
            plain_body = self._create_plain_body(result, event)
            html_body = self._create_html_body(result, event)
            
            msg.attach(MIMEText(plain_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))
            
            # Send email
            context = ssl.create_default_context()
            
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                if self.config.use_tls:
                    server.starttls(context=context)
                server.login(self.config.username, self.config.password)
                server.sendmail(
                    self.config.from_addr,
                    self.config.to_addrs,
                    msg.as_string()
                )
            
            # Update cooldown
            self.last_alert[endpoint_name] = datetime.now().timestamp()
            
            if logger:
                logger.info(f"Email alert sent for {endpoint_name} ({event})")
            
            return True
            
        except Exception as e:
            if logger:
                logger.error(f"Failed to send email alert: {e}")
            return False
    
    def test_connection(self) -> tuple[bool, str]:
        """
        Test SMTP connection.
        
        Returns:
            (success, message) tuple
        """
        try:
            context = ssl.create_default_context()
            
            with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                if self.config.use_tls:
                    server.starttls(context=context)
                server.login(self.config.username, self.config.password)
            
            return True, "Connection successful"
            
        except smtplib.SMTPAuthenticationError:
            return False, "Authentication failed - check username/password"
        except smtplib.SMTPConnectError:
            return False, f"Could not connect to {self.config.smtp_host}:{self.config.smtp_port}"
        except Exception as e:
            return False, str(e)
