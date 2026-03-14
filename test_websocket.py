"""
Testes para WebSocket Server 🦞
"""

import json
import time
import asyncio
import threading
import unittest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock, AsyncMock

# Mock websockets se não estiver disponível
try:
    import websockets
    WEBSOCKETS_AVAILABLE = True
except ImportError:
    WEBSOCKETS_AVAILABLE = False
    # Cria mock do módulo websockets
    import sys
    sys.modules['websockets'] = MagicMock()
    sys.modules['websockets.server'] = MagicMock()

from websocket_server import (
    WebSocketServer, WebSocketClient, WebSocketMessage,
    get_websocket_server, start_websocket_server, stop_websocket_server,
    broadcast_status_update, broadcast_metrics_update, broadcast_alert,
    broadcast_health_check, broadcast_sla_update
)


class TestWebSocketMessage(unittest.TestCase):
    """Testes para WebSocketMessage."""
    
    def test_message_creation(self):
        """Testa criação de mensagem."""
        msg = WebSocketMessage(type='test', data={'key': 'value'})
        
        self.assertEqual(msg.type, 'test')
        self.assertEqual(msg.data, {'key': 'value'})
        self.assertIsInstance(msg.timestamp, datetime)
    
    def test_message_to_json(self):
        """Testa serialização para JSON."""
        msg = WebSocketMessage(type='test', data={'key': 'value'})
        json_str = msg.to_json()
        
        parsed = json.loads(json_str)
        self.assertEqual(parsed['type'], 'test')
        self.assertEqual(parsed['data'], {'key': 'value'})
        self.assertIn('timestamp', parsed)


class TestWebSocketClient(unittest.TestCase):
    """Testes para WebSocketClient."""
    
    def test_client_creation(self):
        """Testa criação de cliente."""
        mock_ws = Mock()
        client = WebSocketClient(
            id='test_client',
            websocket=mock_ws,
            connected_at=datetime.now()
        )
        
        self.assertEqual(client.id, 'test_client')
        self.assertEqual(client.websocket, mock_ws)
        self.assertIsInstance(client.connected_at, datetime)
        self.assertEqual(client.subscriptions, set())
        self.assertIsNone(client.last_ping)
        self.assertEqual(client.metadata, {})


@unittest.skipIf(not WEBSOCKETS_AVAILABLE, "websockets not installed")
class TestWebSocketServer(unittest.TestCase):
    """Testes para WebSocketServer."""
    
    def setUp(self):
        """Setup para cada teste."""
        self.server = WebSocketServer(host='localhost', port=8083)
    
    def tearDown(self):
        """Cleanup após cada teste."""
        if self.server._running:
            self.server.stop()
    
    def test_server_initialization(self):
        """Testa inicialização do servidor."""
        self.assertEqual(self.server.host, 'localhost')
        self.assertEqual(self.server.port, 8083)
        self.assertEqual(self.server.clients, {})
        self.assertEqual(self.server.subscriptions, {})
        self.assertFalse(self.server._running)
    
    def test_stats_initialization(self):
        """Testa stats iniciais."""
        stats = self.server.stats
        
        self.assertEqual(stats['connections_total'], 0)
        self.assertEqual(stats['connections_active'], 0)
        self.assertEqual(stats['messages_sent'], 0)
        self.assertEqual(stats['messages_received'], 0)
        self.assertEqual(stats['errors'], 0)
        self.assertIsNone(stats['started_at'])
    
    def test_get_stats(self):
        """Testa get_stats."""
        stats = self.server.get_stats()
        
        self.assertIn('connections_total', stats)
        self.assertIn('connections_active', stats)
        self.assertIn('clients', stats)
        self.assertIn('subscriptions', stats)
    
    def test_get_client_count(self):
        """Testa get_client_count."""
        self.assertEqual(self.server.get_client_count(), 0)
    
    def test_broadcast_sync_without_running(self):
        """Testa broadcast_sync quando servidor não está rodando."""
        # Não deve levantar exceção
        self.server.broadcast_sync('test', 'test_type', {'key': 'value'})


class TestWebSocketServerMocked(unittest.TestCase):
    """Testes com mocks para WebSocketServer."""
    
    def setUp(self):
        """Setup para cada teste."""
        self.server = WebSocketServer(host='localhost', port=8084)
    
    def test_remove_client(self):
        """Testa remoção de cliente."""
        # Adiciona cliente mock
        mock_ws = Mock()
        client = WebSocketClient(
            id='test_client',
            websocket=mock_ws,
            connected_at=datetime.now(),
            subscriptions={'channel1', 'channel2'}
        )
        
        self.server.clients['test_client'] = client
        self.server.subscriptions['channel1'].add('test_client')
        self.server.subscriptions['channel2'].add('test_client')
        self.server.stats['connections_active'] = 1
        
        # Executa remoção (síncrono para teste)
        asyncio.run(self.server._remove_client('test_client'))
        
        self.assertNotIn('test_client', self.server.clients)
        self.assertNotIn('test_client', self.server.subscriptions['channel1'])
        self.assertNotIn('test_client', self.server.subscriptions['channel2'])
        self.assertEqual(self.server.stats['connections_active'], 0)


class TestGlobalFunctions(unittest.TestCase):
    """Testes para funções globais."""
    
    def setUp(self):
        """Setup para cada teste."""
        # Reset global instance
        import websocket_server
        websocket_server._websocket_server = None
    
    def tearDown(self):
        """Cleanup após cada teste."""
        import websocket_server
        if websocket_server._websocket_server:
            websocket_server._websocket_server.stop()
        websocket_server._websocket_server = None
    
    def test_get_websocket_server_creates_instance(self):
        """Testa criação de instância global."""
        server = get_websocket_server(host='localhost', port=8085)
        
        self.assertIsInstance(server, WebSocketServer)
        self.assertEqual(server.host, 'localhost')
        self.assertEqual(server.port, 8085)
    
    def test_get_websocket_server_returns_same_instance(self):
        """Testa que get retorna mesma instância."""
        server1 = get_websocket_server(host='localhost', port=8086)
        server2 = get_websocket_server()
        
        self.assertIs(server1, server2)
    
    @unittest.skipIf(not WEBSOCKETS_AVAILABLE, "websockets not installed")
    def test_start_stop_websocket_server(self):
        """Testa start/stop do servidor global."""
        server = start_websocket_server(host='localhost', port=8087)
        
        self.assertIsInstance(server, WebSocketServer)
        self.assertTrue(server._running)
        
        stop_websocket_server()
        
        # Verifica que foi parado
        import websocket_server
        self.assertIsNone(websocket_server._websocket_server)


class TestBroadcastFunctions(unittest.TestCase):
    """Testes para funções de broadcast."""
    
    def setUp(self):
        """Setup para cada teste."""
        import websocket_server
        websocket_server._websocket_server = None
    
    def tearDown(self):
        """Cleanup após cada teste."""
        import websocket_server
        if websocket_server._websocket_server:
            websocket_server._websocket_server.stop()
        websocket_server._websocket_server = None
    
    def test_broadcast_status_update(self):
        """Testa broadcast de status update."""
        server = get_websocket_server(host='localhost', port=8088)
        
        # Mock do broadcast_sync
        server.broadcast_sync = Mock()
        
        status = {'api': 'test', 'status': 'online'}
        broadcast_status_update(status)
        
        server.broadcast_sync.assert_called_once_with('status', 'status_update', status)
    
    def test_broadcast_metrics_update(self):
        """Testa broadcast de metrics update."""
        server = get_websocket_server(host='localhost', port=8089)
        server.broadcast_sync = Mock()
        
        metrics = {'cpu': 50, 'memory': 60}
        broadcast_metrics_update(metrics)
        
        server.broadcast_sync.assert_called_once_with('metrics', 'metrics_update', metrics)
    
    def test_broadcast_alert(self):
        """Testa broadcast de alert."""
        server = get_websocket_server(host='localhost', port=8090)
        server.broadcast_sync = Mock()
        
        alert = {'type': 'down', 'api': 'test'}
        broadcast_alert(alert)
        
        server.broadcast_sync.assert_called_once_with('alerts', 'alert', alert)
    
    def test_broadcast_health_check(self):
        """Testa broadcast de health check."""
        server = get_websocket_server(host='localhost', port=8091)
        server.broadcast_sync = Mock()
        
        result = {'check': 'dns', 'status': 'healthy'}
        broadcast_health_check(result)
        
        server.broadcast_sync.assert_called_once_with('health_checks', 'health_check', result)
    
    def test_broadcast_sla_update(self):
        """Testa broadcast de SLA update."""
        server = get_websocket_server(host='localhost', port=8092)
        server.broadcast_sync = Mock()
        
        sla_data = {'endpoint': 'api', 'uptime': 99.9}
        broadcast_sla_update(sla_data)
        
        server.broadcast_sync.assert_called_once_with('sla', 'sla_update', sla_data)


class TestWebSocketIntegration(unittest.TestCase):
    """Testes de integração para WebSocket."""
    
    def test_message_flow(self):
        """Testa fluxo de mensagens."""
        msg = WebSocketMessage(
            type='status_update',
            data={'api': 'test', 'status': 'online'}
        )
        
        # Serializa
        json_str = msg.to_json()
        
        # Deserializa
        parsed = json.loads(json_str)
        
        self.assertEqual(parsed['type'], 'status_update')
        self.assertEqual(parsed['data']['api'], 'test')
        self.assertEqual(parsed['data']['status'], 'online')
    
    def test_subscription_management(self):
        """Testa gerenciamento de subscriptions."""
        server = WebSocketServer(host='localhost', port=8093)
        
        # Simula cliente
        mock_ws = Mock()
        client = WebSocketClient(
            id='test_client',
            websocket=mock_ws,
            connected_at=datetime.now()
        )
        
        server.clients['test_client'] = client
        
        # Adiciona subscriptions manualmente
        client.subscriptions.add('status')
        client.subscriptions.add('metrics')
        server.subscriptions['status'].add('test_client')
        server.subscriptions['metrics'].add('test_client')
        
        # Verifica
        self.assertEqual(len(client.subscriptions), 2)
        self.assertIn('test_client', server.subscriptions['status'])
        self.assertIn('test_client', server.subscriptions['metrics'])


if __name__ == '__main__':
    unittest.main()
