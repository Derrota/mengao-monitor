#!/usr/bin/env python3
"""
Mengão Monitor 🦞
Monitor de APIs simples e eficiente.
"""

import json
import time
import logging
import requests
from datetime import datetime
from typing import Dict, List, Optional

class APIMonitor:
    def __init__(self, config_file: str = "config.json"):
        self.config = self.load_config(config_file)
        self.setup_logging()
        
    def load_config(self, config_file: str) -> Dict:
        """Carrega configuração do arquivo JSON."""
        try:
            with open(config_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            print(f"❌ Arquivo {config_file} não encontrado!")
            print("📝 Copie config.example.json para config.json e edite com suas APIs.")
            exit(1)
        except json.JSONDecodeError:
            print(f"❌ Erro ao ler {config_file}. Verifique o formato JSON.")
            exit(1)
    
    def setup_logging(self):
        """Configura logging."""
        log_file = self.config.get('log_file', 'monitor.log')
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(log_file),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def check_api(self, api_config: Dict) -> Dict:
        """Verifica se uma API está online."""
        name = api_config.get('name', 'API sem nome')
        url = api_config.get('url')
        method = api_config.get('method', 'GET').upper()
        timeout = api_config.get('timeout', 5)
        expected_status = api_config.get('expected_status', 200)
        
        result = {
            'name': name,
            'url': url,
            'status': 'unknown',
            'response_time': None,
            'error': None,
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            start_time = time.time()
            response = requests.request(
                method=method,
                url=url,
                timeout=timeout
            )
            response_time = round(time.time() - start_time, 3)
            
            result['response_time'] = response_time
            
            if response.status_code == expected_status:
                result['status'] = 'online'
                self.logger.info(f"✅ {name} - Online ({response_time}s)")
            else:
                result['status'] = 'error'
                result['error'] = f"Status {response.status_code} (esperado {expected_status})"
                self.logger.warning(f"⚠️  {name} - Status inesperado: {response.status_code}")
                
        except requests.exceptions.Timeout:
            result['status'] = 'timeout'
            result['error'] = f"Timeout após {timeout}s"
            self.logger.error(f"⏰ {name} - Timeout")
            
        except requests.exceptions.ConnectionError:
            result['status'] = 'offline'
            result['error'] = "Erro de conexão"
            self.logger.error(f"❌ {name} - Offline")
            
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            self.logger.error(f"❌ {name} - Erro: {e}")
        
        return result
    
    def send_webhook(self, result: Dict):
        """Envia alerta via webhook."""
        webhook_url = self.config.get('webhook_url')
        if not webhook_url:
            return
        
        # Só envia alerta se a API não estiver online
        if result['status'] == 'online':
            return
        
        # Formata mensagem baseada no status
        if result['status'] == 'offline':
            emoji = '❌'
            color = 0xFF0000  # Vermelho
        elif result['status'] == 'timeout':
            emoji = '⏰'
            color = 0xFFA500  # Laranja
        else:
            emoji = '⚠️'
            color = 0xFFFF00  # Amarelo
        
        # Payload para Discord
        payload = {
            "embeds": [{
                "title": f"{emoji} {result['name']} - {result['status'].upper()}",
                "description": f"**URL:** {result['url']}\n**Erro:** {result['error']}",
                "color": color,
                "timestamp": result['timestamp']
            }]
        }
        
        try:
            requests.post(webhook_url, json=payload, timeout=5)
            self.logger.info(f"📤 Webhook enviado para {result['name']}")
        except Exception as e:
            self.logger.error(f"❌ Erro ao enviar webhook: {e}")
    
    def run(self):
        """Loop principal do monitor."""
        self.logger.info("🦞 Mengão Monitor iniciado!")
        self.logger.info(f"📊 Monitorando {len(self.config['apis'])} APIs")
        self.logger.info(f"⏱️  Intervalo: {self.config['check_interval']}s")
        
        while True:
            self.logger.info("🔍 Iniciando verificação...")
            
            for api_config in self.config['apis']:
                result = self.check_api(api_config)
                self.send_webhook(result)
            
            self.logger.info(f"💤 Próxima verificação em {self.config['check_interval']}s")
            time.sleep(self.config['check_interval'])

if __name__ == "__main__":
    monitor = APIMonitor()
    monitor.run()
