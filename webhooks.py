"""
Multi-webhook support para Mengão Monitor v1.6 🦞
Suporte a Discord, Slack e Telegram com retry automático.
"""

import time
import requests
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from rate_limiter import RateLimiter, RateLimitConfig


@dataclass
class WebhookResult:
    """Resultado de um envio de webhook."""
    success: bool
    platform: str
    status_code: Optional[int] = None
    error: Optional[str] = None
    attempts: int = 1


class WebhookSender:
    """Gerencia envio de alertas para múltiplas plataformas com retry e rate limiting."""
    
    # Configurações de retry
    MAX_RETRIES = 3
    RETRY_DELAYS = [1, 3, 5]  # segundos entre tentativas
    REQUEST_TIMEOUT = 10  # timeout por request
    
    def __init__(self, webhooks: List[Dict], rate_limit_config: Optional[RateLimitConfig] = None):
        """
        Args:
            webhooks: Lista de configs de webhook
            rate_limit_config: Configuração de rate limiting (opcional)
        """
        self.webhooks = [wh for wh in (webhooks or []) if wh.get('enabled', True)]
        self.cooldowns: Dict[str, datetime] = {}  # {api_name: last_alert_time}
        self.cooldown_seconds = 300  # 5 min entre alertas do mesmo endpoint
        
        # Rate limiter
        self.rate_limiter = RateLimiter(rate_limit_config or RateLimitConfig())
        
        self.stats = {
            'sent': 0,
            'failed': 0,
            'retries': 0,
            'cooldown_skipped': 0,
            'rate_limited': 0
        }
    
    def _in_cooldown(self, api_name: str) -> bool:
        """Verifica se API está em cooldown."""
        last_alert = self.cooldowns.get(api_name)
        if not last_alert:
            return False
        
        elapsed = (datetime.now() - last_alert).total_seconds()
        return elapsed < self.cooldown_seconds
    
    def _request_with_retry(self, method: str, url: str, **kwargs) -> Tuple[bool, Optional[int], Optional[str]]:
        """
        Faz request com retry automático.
        
        Returns:
            (success, status_code, error_message)
        """
        kwargs.setdefault('timeout', self.REQUEST_TIMEOUT)
        
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                resp = requests.request(method, url, **kwargs)
                
                # 2xx = sucesso
                if 200 <= resp.status_code < 300:
                    return True, resp.status_code, None
                
                # 4xx = erro do cliente (não retry)
                if 400 <= resp.status_code < 500:
                    return False, resp.status_code, f"Client error: {resp.status_code}"
                
                # 5xx = erro do servidor (retry)
                last_error = f"Server error: {resp.status_code}"
                
            except requests.exceptions.Timeout:
                last_error = "Request timeout"
            except requests.exceptions.ConnectionError as e:
                last_error = f"Connection error: {str(e)[:100]}"
            except Exception as e:
                last_error = f"Unexpected error: {str(e)[:100]}"
            
            # Retry com backoff (exceto última tentativa)
            if attempt < self.MAX_RETRIES - 1:
                self.stats['retries'] += 1
                time.sleep(self.RETRY_DELAYS[attempt])
        
        return False, None, last_error
    
    def _format_discord(self, result: Dict) -> Dict:
        """Formata payload para Discord."""
        status = result.get('status', 'unknown')
        
        if status in ('offline', 'down'):
            emoji = '🔴'
            color = 0xFF0000
        elif status == 'timeout':
            emoji = '🟡'
            color = 0xFFA500
        elif status == 'online':
            emoji = '🟢'
            color = 0x00FF00
        else:
            emoji = '⚠️'
            color = 0xFFFF00
        
        fields = [
            {"name": "URL", "value": f"`{result['url']}`", "inline": False},
            {"name": "Status", "value": f"{emoji} {status.upper()}", "inline": True},
        ]
        
        if result.get('error'):
            fields.append({"name": "Erro", "value": f"```{result['error'][:500]}```", "inline": False})
        
        if result.get('response_time_ms'):
            fields.append({"name": "Response Time", "value": f"{result['response_time_ms']:.0f}ms", "inline": True})
        
        return {
            "embeds": [{
                "title": f"{emoji} {result['name']} - {status.upper()}",
                "fields": fields,
                "color": color,
                "timestamp": result.get('timestamp', datetime.now().isoformat()),
                "footer": {"text": "🦞 Mengão Monitor v1.6"}
            }]
        }
    
    def _format_slack(self, result: Dict) -> Dict:
        """Formata payload para Slack."""
        status = result.get('status', 'unknown')
        
        if status in ('offline', 'down'):
            emoji = ':red_circle:'
        elif status == 'timeout':
            emoji = ':large_yellow_circle:'
        elif status == 'online':
            emoji = ':large_green_circle:'
        else:
            emoji = ':warning:'
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {result['name']} - {status.upper()}"
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*URL:*\n`{result['url']}`"},
                    {"type": "mrkdwn", "text": f"*Status:*\n{status.upper()}"}
                ]
            }
        ]
        
        if result.get('error'):
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Erro:*\n```{result['error'][:500]}```"}
            })
        
        blocks.append({
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"🦞 Mengão Monitor v1.6 | {result.get('timestamp', '')}"}
            ]
        })
        
        return {"blocks": blocks}
    
    def _format_telegram(self, result: Dict, chat_id: str) -> Dict:
        """Formata payload para Telegram."""
        status = result.get('status', 'unknown')
        
        if status in ('offline', 'down'):
            emoji = '🔴'
        elif status == 'timeout':
            emoji = '🟡'
        elif status == 'online':
            emoji = '🟢'
        else:
            emoji = '⚠️'
        
        lines = [
            f"{emoji} *{result['name']} - {status.upper()}*",
            "",
            f"🔗 URL: `{result['url']}`",
        ]
        
        if result.get('error'):
            lines.append(f"💥 Erro: {result['error'][:200]}")
        
        if result.get('response_time_ms'):
            lines.append(f"⏱ Response: {result['response_time_ms']:.0f}ms")
        
        lines.extend(["", "🦞 Mengão Monitor v1.6"])
        
        return {
            "chat_id": chat_id,
            "text": "\n".join(lines),
            "parse_mode": "Markdown"
        }
    
    def send(self, result: Dict, logger=None) -> List[WebhookResult]:
        """
        Envia alerta para todos os webhooks configurados.
        
        Returns:
            Lista de WebhookResult com status de cada envio
        """
        results = []
        
        # Só alerta se não estiver online (ou se for recovery)
        if result['status'] == 'online':
            return results
        
        api_name = result['name']
        
        # Verifica rate limit
        if not self.rate_limiter.allow_alert(api_name):
            self.stats['rate_limited'] += 1
            if logger:
                logger.warning(f"🚫 {api_name} bloqueado por rate limit")
            return results
        
        # Verifica cooldown (mantido para compatibilidade)
        if self._in_cooldown(api_name):
            self.stats['cooldown_skipped'] += 1
            if logger:
                logger.debug(f"⏳ {api_name} em cooldown, pulando alerta")
            return results
        
        sent_count = 0
        
        for webhook in self.webhooks:
            wh_type = webhook.get('type', 'discord').lower()
            wh_url = webhook.get('url')
            
            if not wh_url:
                continue
            
            wh_result = self._send_single(wh_type, wh_url, result, webhook)
            results.append(wh_result)
            
            if wh_result.success:
                sent_count += 1
                self.stats['sent'] += 1
                if logger:
                    logger.info(f"📤 Webhook {wh_type} enviado para {api_name}")
            else:
                self.stats['failed'] += 1
                if logger:
                    logger.error(f"❌ Webhook {wh_type} falhou: {wh_result.error}")
        
        # Atualiza cooldown se enviou pelo menos 1
        if sent_count > 0:
            self.cooldowns[api_name] = datetime.now()
        
        return results
    
    def _send_single(self, wh_type: str, wh_url: str, result: Dict, webhook: Dict) -> WebhookResult:
        """Envia para um único webhook com retry."""
        try:
            if wh_type == 'discord':
                payload = self._format_discord(result)
                success, status_code, error = self._request_with_retry('POST', wh_url, json=payload)
                
            elif wh_type == 'slack':
                payload = self._format_slack(result)
                success, status_code, error = self._request_with_retry('POST', wh_url, json=payload)
                
            elif wh_type == 'telegram':
                chat_id = webhook.get('chat_id')
                if not chat_id:
                    return WebhookResult(False, wh_type, error="Missing chat_id")
                
                payload = self._format_telegram(result, chat_id)
                tg_url = f"{wh_url.rstrip('/')}/sendMessage"
                success, status_code, error = self._request_with_retry('POST', tg_url, json=payload)
                
            else:
                return WebhookResult(False, wh_type, error=f"Unknown type: {wh_type}")
            
            return WebhookResult(
                success=success,
                platform=wh_type,
                status_code=status_code,
                error=error,
                attempts=self.MAX_RETRIES if not success else 1
            )
            
        except Exception as e:
            return WebhookResult(False, wh_type, error=str(e)[:200])
    
    def get_stats(self) -> Dict:
        """Retorna estatísticas de envio."""
        stats = self.stats.copy()
        stats['rate_limiter'] = self.rate_limiter.get_stats()
        return stats
    
    def get_rate_limit_status(self, endpoint_name: str) -> Dict:
        """Retorna status do rate limit para um endpoint."""
        return {
            'remaining': self.rate_limiter.get_remaining(endpoint_name),
            'stats': self.rate_limiter.get_stats()
        }
    
    def reset_stats(self):
        """Reseta estatísticas."""
        self.stats = {'sent': 0, 'failed': 0, 'retries': 0, 'cooldown_skipped': 0, 'rate_limited': 0}
        self.rate_limiter.reset_stats()
