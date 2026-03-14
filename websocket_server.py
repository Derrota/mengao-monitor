"""
WebSocket Server para Mengão Monitor v3.0 🦞
Updates em tempo real para o dashboard.
"""

import json
import asyncio
import threading
import time
from datetime import datetime
from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict

try:
    import websockets
    from websockets.server import serve, WebSocketServerProtocol
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    # Type stubs para quando websockets não está disponível
    class WebSocketServerProtocol:
        pass


@dataclass
class WebSocketClient:
    """Cliente WebSocket conectado."""
    id: str
    websocket: WebSocketServerProtocol
    connected_at: datetime
    subscriptions: Set[str] = field(default_factory=set)
    last_ping: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WebSocketMessage:
    """Mensagem WebSocket."""
    type: str
    data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_json(self) -> str:
        return json.dumps({
            'type': self.type,
            'data': self.data,
            'timestamp': self.timestamp.isoformat()
        })


class WebSocketServer:
    """Servidor WebSocket para updates em tempo real."""
    
    def __init__(self, host: str = 'localhost', port: int = 8082, 
                 ping_interval: int = 30, ping_timeout: int = 10):
        """
        Args:
            host: Host para bind
            port: Porta para bind
            ping_interval: Intervalo de ping em segundos
            ping_timeout: Timeout de ping em segundos
        """
        if not WEBSOCKETS_AVAILABLE:
            raise ImportError("websockets library not installed. Run: pip install websockets")
        
        self.host = host
        self.port = port
        self.ping_interval = ping_interval
        self.ping_timeout = ping_timeout
        
        self.clients: Dict[str, WebSocketClient] = {}
        self.subscriptions: Dict[str, Set[str]] = defaultdict(set)  # channel -> client_ids
        self.message_history: List[WebSocketMessage] = []
        self.max_history = 100
        
        self._server = None
        self._thread = None
        self._loop = None
        self._running = False
        
        # Stats
        self.stats = {
            'connections_total': 0,
            'connections_active': 0,
            'messages_sent': 0,
            'messages_received': 0,
            'errors': 0,
            'started_at': None
        }
    
    async def _handler(self, websocket: WebSocketServerProtocol, path: str):
        """Handler para novas conexões WebSocket."""
        client_id = f"client_{int(time.time() * 1000)}_{id(websocket)}"
        client = WebSocketClient(
            id=client_id,
            websocket=websocket,
            connected_at=datetime.now()
        )
        
        self.clients[client_id] = client
        self.stats['connections_total'] += 1
        self.stats['connections_active'] += 1
        
        print(f"🔗 WebSocket client connected: {client_id}")
        
        try:
            # Envia mensagem de boas-vindas
            await self._send_to_client(client, WebSocketMessage(
                type='welcome',
                data={
                    'client_id': client_id,
                    'server_time': datetime.now().isoformat(),
                    'available_channels': ['status', 'metrics', 'alerts', 'health_checks', 'sla']
                }
            ))
            
            # Processa mensagens do cliente
            async for message in websocket:
                await self._handle_client_message(client, message)
                
        except websockets.exceptions.ConnectionClosed:
            print(f"🔌 WebSocket client disconnected: {client_id}")
        except Exception as e:
            print(f"❌ WebSocket error for {client_id}: {e}")
            self.stats['errors'] += 1
        finally:
            await self._remove_client(client_id)
    
    async def _handle_client_message(self, client: WebSocketClient, message: str):
        """Processa mensagem recebida do cliente."""
        self.stats['messages_received'] += 1
        
        try:
            data = json.loads(message)
            msg_type = data.get('type', '')
            
            if msg_type == 'subscribe':
                channels = data.get('channels', [])
                await self._subscribe_client(client, channels)
                
            elif msg_type == 'unsubscribe':
                channels = data.get('channels', [])
                await self._unsubscribe_client(client, channels)
                
            elif msg_type == 'ping':
                client.last_ping = datetime.now()
                await self._send_to_client(client, WebSocketMessage(
                    type='pong',
                    data={'timestamp': datetime.now().isoformat()}
                ))
                
            elif msg_type == 'get_history':
                channel = data.get('channel')
                limit = data.get('limit', 10)
                await self._send_history(client, channel, limit)
                
            else:
                await self._send_to_client(client, WebSocketMessage(
                    type='error',
                    data={'message': f'Unknown message type: {msg_type}'}
                ))
                
        except json.JSONDecodeError:
            await self._send_to_client(client, WebSocketMessage(
                type='error',
                data={'message': 'Invalid JSON'}
            ))
        except Exception as e:
            await self._send_to_client(client, WebSocketMessage(
                type='error',
                data={'message': str(e)}
            ))
    
    async def _subscribe_client(self, client: WebSocketClient, channels: List[str]):
        """Inscreve cliente em canais."""
        subscribed = []
        for channel in channels:
            client.subscriptions.add(channel)
            self.subscriptions[channel].add(client.id)
            subscribed.append(channel)
        
        await self._send_to_client(client, WebSocketMessage(
            type='subscribed',
            data={'channels': subscribed}
        ))
        
        print(f"📺 Client {client.id} subscribed to: {subscribed}")
    
    async def _unsubscribe_client(self, client: WebSocketClient, channels: List[str]):
        """Desinscreve cliente de canais."""
        unsubscribed = []
        for channel in channels:
            client.subscriptions.discard(channel)
            self.subscriptions[channel].discard(client.id)
            unsubscribed.append(channel)
        
        await self._send_to_client(client, WebSocketMessage(
            type='unsubscribed',
            data={'channels': unsubscribed}
        ))
    
    async def _send_history(self, client: WebSocketClient, channel: Optional[str], limit: int):
        """Envia histórico de mensagens para o cliente."""
        history = self.message_history[-limit:]
        if channel:
            history = [msg for msg in history if msg.data.get('channel') == channel]
        
        await self._send_to_client(client, WebSocketMessage(
            type='history',
            data={
                'messages': [
                    {
                        'type': msg.type,
                        'data': msg.data,
                        'timestamp': msg.timestamp.isoformat()
                    }
                    for msg in history
                ]
            }
        ))
    
    async def _send_to_client(self, client: WebSocketClient, message: WebSocketMessage):
        """Envia mensagem para um cliente específico."""
        try:
            await client.websocket.send(message.to_json())
            self.stats['messages_sent'] += 1
        except Exception as e:
            print(f"❌ Error sending to {client.id}: {e}")
            self.stats['errors'] += 1
    
    async def _remove_client(self, client_id: str):
        """Remove cliente da conexão."""
        if client_id in self.clients:
            client = self.clients[client_id]
            
            # Remove de todas as subscriptions
            for channel in client.subscriptions:
                self.subscriptions[channel].discard(client_id)
            
            del self.clients[client_id]
            self.stats['connections_active'] -= 1
            
            print(f"🗑️ Client removed: {client_id}")
    
    async def broadcast(self, channel: str, message: WebSocketMessage):
        """Broadcast mensagem para todos os clientes inscritos em um canal."""
        if channel not in self.subscriptions:
            return
        
        # Adiciona ao histórico
        self.message_history.append(message)
        if len(self.message_history) > self.max_history:
            self.message_history.pop(0)
        
        # Envia para todos os clientes inscritos
        client_ids = list(self.subscriptions[channel])
        for client_id in client_ids:
            if client_id in self.clients:
                client = self.clients[client_id]
                await self._send_to_client(client, message)
    
    def broadcast_sync(self, channel: str, message_type: str, data: Dict[str, Any]):
        """Versão síncrona do broadcast (para uso fora do loop asyncio)."""
        if not self._loop or not self._running:
            return
        
        message = WebSocketMessage(type=message_type, data={**data, 'channel': channel})
        
        # Agenda broadcast no loop asyncio
        asyncio.run_coroutine_threadsafe(
            self.broadcast(channel, message),
            self._loop
        )
    
    def start(self):
        """Inicia o servidor WebSocket em uma thread separada."""
        if self._running:
            print("⚠️ WebSocket server already running")
            return
        
        self._running = True
        self.stats['started_at'] = datetime.now()
        
        def run_server():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            
            async def start_server():
                self._server = await serve(
                    self._handler,
                    self.host,
                    self.port,
                    ping_interval=self.ping_interval,
                    ping_timeout=self.ping_timeout
                )
                print(f"🚀 WebSocket server started on ws://{self.host}:{self.port}")
                
                # Mantém o servidor rodando
                await asyncio.Future()  # run forever
            
            try:
                self._loop.run_until_complete(start_server())
            except Exception as e:
                print(f"❌ WebSocket server error: {e}")
                self._running = False
        
        self._thread = threading.Thread(target=run_server, daemon=True)
        self._thread.start()
        
        # Aguarda um pouco para garantir que o servidor iniciou
        time.sleep(0.5)
    
    def stop(self):
        """Para o servidor WebSocket."""
        if not self._running:
            return
        
        self._running = False
        
        if self._server:
            self._server.close()
        
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        
        if self._thread:
            self._thread.join(timeout=5)
        
        print("🛑 WebSocket server stopped")
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do servidor."""
        stats = self.stats.copy()
        stats['clients'] = {
            client_id: {
                'connected_at': client.connected_at.isoformat(),
                'subscriptions': list(client.subscriptions),
                'last_ping': client.last_ping.isoformat() if client.last_ping else None
            }
            for client_id, client in self.clients.items()
        }
        stats['subscriptions'] = {
            channel: list(client_ids)
            for channel, client_ids in self.subscriptions.items()
        }
        return stats
    
    def get_client_count(self) -> int:
        """Retorna número de clientes conectados."""
        return len(self.clients)


# Instância global (singleton)
_websocket_server: Optional[WebSocketServer] = None


def get_websocket_server(host: str = 'localhost', port: int = 8082) -> WebSocketServer:
    """Retorna instância global do servidor WebSocket."""
    global _websocket_server
    if _websocket_server is None:
        _websocket_server = WebSocketServer(host=host, port=port)
    return _websocket_server


def start_websocket_server(host: str = 'localhost', port: int = 8082) -> WebSocketServer:
    """Inicia servidor WebSocket global."""
    server = get_websocket_server(host, port)
    server.start()
    return server


def stop_websocket_server():
    """Para servidor WebSocket global."""
    global _websocket_server
    if _websocket_server:
        _websocket_server.stop()
        _websocket_server = None


# Funções de conveniência para broadcast
def broadcast_status_update(status: Dict[str, Any]):
    """Broadcast update de status."""
    server = get_websocket_server()
    server.broadcast_sync('status', 'status_update', status)


def broadcast_metrics_update(metrics: Dict[str, Any]):
    """Broadcast update de métricas."""
    server = get_websocket_server()
    server.broadcast_sync('metrics', 'metrics_update', metrics)


def broadcast_alert(alert: Dict[str, Any]):
    """Broadcast alerta."""
    server = get_websocket_server()
    server.broadcast_sync('alerts', 'alert', alert)


def broadcast_health_check(result: Dict[str, Any]):
    """Broadcast resultado de health check."""
    server = get_websocket_server()
    server.broadcast_sync('health_checks', 'health_check', result)


def broadcast_sla_update(sla_data: Dict[str, Any]):
    """Broadcast update de SLA."""
    server = get_websocket_server()
    server.broadcast_sync('sla', 'sla_update', sla_data)
