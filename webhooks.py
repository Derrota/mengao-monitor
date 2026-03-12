"""
Multi-webhook support para Mengão Monitor 🦞
Suporte a Discord, Slack e Telegram.
"""

import requests
from datetime import datetime
from typing import Dict, List, Optional


class WebhookSender:
    """Gerencia envio de alertas para múltiplas plataformas."""
    
    def __init__(self, webhooks: List[Dict]):
        """
        Args:
            webhooks: Lista de configs de webhook
            [
                {"type": "discord", "url": "..."},
                {"type": "slack", "url": "..."},
                {"type": "telegram", "url": "...", "chat_id": "..."}
            ]
        """
        self.webhooks = webhooks or []
        self.cooldowns = {}  # {api_name: last_alert_time}
        self.cooldown_seconds = 300  # 5 min entre alertas do mesmo endpoint
    
    def _in_cooldown(self, api_name: str) -> bool:
        """Verifica se API está em cooldown."""
        last_alert = self.cooldowns.get(api_name)
        if not last_alert:
            return False
        
        elapsed = (datetime.now() - last_alert).total_seconds()
        return elapsed < self.cooldown_seconds
    
    def _format_discord(self, result: Dict) -> Dict:
        """Formata payload para Discord."""
        if result['status'] == 'offline':
            emoji = '❌'
            color = 0xFF0000
        elif result['status'] == 'timeout':
            emoji = '⏰'
            color = 0xFFA500
        else:
            emoji = '⚠️'
            color = 0xFFFF00
        
        return {
            "embeds": [{
                "title": f"{emoji} {result['name']} - {result['status'].upper()}",
                "description": f"**URL:** {result['url']}\n**Erro:** {result['error']}",
                "color": color,
                "timestamp": result['timestamp'],
                "footer": {"text": "🦞 Mengão Monitor"}
            }]
        }
    
    def _format_slack(self, result: Dict) -> Dict:
        """Formata payload para Slack."""
        if result['status'] == 'offline':
            emoji = ':x:'
        elif result['status'] == 'timeout':
            emoji = ':clock:'
        else:
            emoji = ':warning:'
        
        return {
            "blocks": [
                {
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": f"{emoji} {result['name']} - {result['status'].upper()}"
                    }
                },
                {
                    "type": "section",
                    "fields": [
                        {"type": "mrkdwn", "text": f"*URL:*\n{result['url']}"},
                        {"type": "mrkdwn", "text": f"*Erro:*\n{result['error']}"}
                    ]
                },
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"🦞 Mengão Monitor | {result['timestamp']}"}
                    ]
                }
            ]
        }
    
    def _format_telegram(self, result: Dict, chat_id: str) -> Dict:
        """Formata payload para Telegram."""
        if result['status'] == 'offline':
            emoji = '❌'
        elif result['status'] == 'timeout':
            emoji = '⏰'
        else:
            emoji = '⚠️'
        
        text = (
            f"{emoji} *{result['name']} - {result['status'].upper()}*\n\n"
            f"🔗 URL: `{result['url']}`\n"
            f"💥 Erro: {result['error']}\n\n"
            f"🦞 Mengão Monitor"
        )
        
        return {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
    
    def send(self, result: Dict, logger=None):
        """Envia alerta para todos os webhooks configurados."""
        # Só alerta se não estiver online
        if result['status'] == 'online':
            return
        
        # Verifica cooldown
        api_name = result['name']
        if self._in_cooldown(api_name):
            if logger:
                logger.debug(f"⏳ {api_name} em cooldown, pulando alerta")
            return
        
        sent_count = 0
        for webhook in self.webhooks:
            wh_type = webhook.get('type', 'discord').lower()
            wh_url = webhook.get('url')
            
            if not wh_url:
                continue
            
            try:
                if wh_type == 'discord':
                    payload = self._format_discord(result)
                    resp = requests.post(wh_url, json=payload, timeout=5)
                    
                elif wh_type == 'slack':
                    payload = self._format_slack(result)
                    resp = requests.post(wh_url, json=payload, timeout=5)
                    
                elif wh_type == 'telegram':
                    chat_id = webhook.get('chat_id')
                    if not chat_id:
                        continue
                    payload = self._format_telegram(result, chat_id)
                    # URL do Telegram é diferente
                    tg_url = f"{wh_url}/sendMessage"
                    resp = requests.post(tg_url, json=payload, timeout=5)
                    
                else:
                    if logger:
                        logger.warning(f"⚠️ Tipo de webhook desconhecido: {wh_type}")
                    continue
                
                if resp.status_code in [200, 204]:
                    sent_count += 1
                    if logger:
                        logger.info(f"📤 Webhook {wh_type} enviado para {api_name}")
                else:
                    if logger:
                        logger.error(f"❌ Webhook {wh_type} falhou: {resp.status_code}")
                        
            except Exception as e:
                if logger:
                    logger.error(f"❌ Erro webhook {wh_type}: {e}")
        
        # Atualiza cooldown se enviou pelo menos 1
        if sent_count > 0:
            self.cooldowns[api_name] = datetime.now()
