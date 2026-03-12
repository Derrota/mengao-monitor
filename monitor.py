#!/usr/bin/env python3
"""
Mengão Monitor v1.2 🦞
Monitor de APIs simples, eficiente e rubro-negro.
"""

import json
import time
import logging
import requests
import argparse
from datetime import datetime
from typing import Dict, List, Optional

from health import update_state, start_health_server
from webhooks import WebhookSender
from history import UptimeHistory


class APIMonitor:
    def __init__(self, config_file: str = "config.json", enable_health: bool = False, health_port: int = 8080):
        self.config = self.load_config(config_file)
        self.setup_logging()
        
        # Multi-webhook support
        webhooks_config = self._parse_webhooks()
        self.webhook_sender = WebhookSender(webhooks_config)
        self.webhook_sender.cooldown_seconds = self.config.get('webhook_cooldown', 300)
        
        # Uptime history
        db_path = self.config.get('history_db', 'uptime.db')
        self.history = UptimeHistory(db_path)
        
        # Estado interno
        self.state = {
            'started_at': datetime.now(),
            'last_check': None,
            'checks_count': 0,
            'apis_monitored': len(self.config.get('apis', [])),
            'errors_count': 0,
            'apis': []
        }
        
        # Inicia health check server se habilitado
        if enable_health:
            self.logger.info(f"🏥 Health check habilitado na porta {health_port}")
            start_health_server(health_port)
            update_state(
                started_at=self.state['started_at'],
                apis_monitored=self.state['apis_monitored']
            )
    
    def _parse_webhooks(self) -> List[Dict]:
        """Converte config de webhooks para formato padrão."""
        webhooks = []
        
        # Novo formato: lista de webhooks
        if 'webhooks' in self.config:
            for wh in self.config['webhooks']:
                webhooks.append(wh)
        
        # Formato legado: webhook_url (Discord)
        elif self.config.get('webhook_url'):
            webhooks.append({
                'type': 'discord',
                'url': self.config['webhook_url']
            })
        
        return webhooks
    
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
        log_level = self.config.get('log_level', 'INFO').upper()
        
        logging.basicConfig(
            level=getattr(logging, log_level, logging.INFO),
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
    
    def send_alert(self, result: Dict):
        """Envia alerta via webhooks (com cooldown)."""
        self.webhook_sender.send(result, self.logger)
    
    def record_history(self, result: Dict):
        """Registra verificação no histórico."""
        try:
            self.history.record_check(result)
        except Exception as e:
            self.logger.error(f"❌ Erro ao salvar histórico: {e}")
    
    def get_api_stats(self, api_name: str) -> Dict:
        """Retorna stats de uma API do histórico."""
        try:
            uptime = self.history.get_uptime(api_name, hours=24)
            avg_time = self.history.get_avg_response_time(api_name, hours=24)
            recent = self.history.get_recent_checks(api_name, limit=1)
            
            return {
                'uptime': uptime,
                'avg_response_time': avg_time,
                'checks': len(recent)
            }
        except:
            return {'uptime': 0, 'avg_response_time': None, 'checks': 0}
    
    def run(self):
        """Loop principal do monitor."""
        self.logger.info("🦞 Mengão Monitor v1.2 iniciado!")
        self.logger.info(f"📊 Monitorando {len(self.config['apis'])} APIs")
        self.logger.info(f"⏱️  Intervalo: {self.config['check_interval']}s")
        self.logger.info(f"📤 Webhooks: {len(self.webhook_sender.webhooks)} configurados")
        self.logger.info(f"💾 Histórico: {self.history.db_path}")
        
        while True:
            self.logger.info("🔍 Iniciando verificação...")
            
            errors_in_check = 0
            apis_status = []
            
            for api_config in self.config['apis']:
                result = self.check_api(api_config)
                
                # Envia alerta (com cooldown)
                self.send_alert(result)
                
                # Registra no histórico
                self.record_history(result)
                
                # Coleta stats
                stats = self.get_api_stats(result['name'])
                
                # Monta status para dashboard
                apis_status.append({
                    'name': result['name'],
                    'url': result['url'],
                    'status': result['status'],
                    'response_time': result['response_time'],
                    'uptime': stats['uptime'],
                    'checks': stats['checks']
                })
                
                if result['status'] != 'online':
                    errors_in_check += 1
            
            # Atualiza estado
            self.state['checks_count'] += 1
            self.state['last_check'] = datetime.now().isoformat()
            self.state['errors_count'] += errors_in_check
            self.state['apis'] = apis_status
            
            # Sincroniza com health server
            update_state(
                last_check=self.state['last_check'],
                checks_count=self.state['checks_count'],
                errors_count=self.state['errors_count'],
                apis=apis_status
            )
            
            # Cleanup periódico (a cada 100 checks)
            if self.state['checks_count'] % 100 == 0:
                deleted = self.history.cleanup_old_records(days=30)
                if deleted > 0:
                    self.logger.info(f"🧹 Cleanup: {deleted} registros antigos removidos")
            
            self.logger.info(f"💤 Próxima verificação em {self.config['check_interval']}s")
            time.sleep(self.config['check_interval'])


def main():
    """Entry point com argumentos de linha de comando."""
    parser = argparse.ArgumentParser(
        description='🦞 Mengão Monitor v1.2 - Monitor de APIs simples e eficiente'
    )
    parser.add_argument(
        '-c', '--config',
        default='config.json',
        help='Arquivo de configuração (default: config.json)'
    )
    parser.add_argument(
        '--health',
        action='store_true',
        help='Habilita health check endpoint'
    )
    parser.add_argument(
        '--health-port',
        type=int,
        default=8080,
        help='Porta do health check (default: 8080)'
    )
    parser.add_argument(
        '--export-csv',
        metavar='FILE',
        help='Exporta histórico para CSV e sai'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Mostra estatísticas e sai'
    )
    
    args = parser.parse_args()
    
    # Comandos one-shot
    if args.export_csv:
        config = json.load(open(args.config))
        history = UptimeHistory(config.get('history_db', 'uptime.db'))
        count = history.export_csv(args.export_csv, hours=24)
        print(f"📊 {count} registros exportados para {args.export_csv}")
        return
    
    if args.stats:
        config = json.load(open(args.config))
        history = UptimeHistory(config.get('history_db', 'uptime.db'))
        stats = history.get_all_apis_stats(hours=24)
        
        print("🦞 Mengão Monitor - Estatísticas (24h)\n")
        for api_name, data in stats.items():
            print(f"📊 {api_name}")
            print(f"   Uptime: {data['uptime_percent']}%")
            print(f"   Checks: {data['total_checks']}")
            print(f"   Avg Response: {data['avg_response_time'] or 'N/A'}s")
            print(f"   Último check: {data['last_check']}")
            print()
        return
    
    # Modo normal: monitor loop
    monitor = APIMonitor(
        config_file=args.config,
        enable_health=args.health,
        health_port=args.health_port
    )
    monitor.run()


if __name__ == "__main__":
    main()
