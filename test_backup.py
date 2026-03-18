"""
Testes para o Backup System v3.14.
"""

import os
import time
import sqlite3
import tempfile
import shutil
import unittest
from unittest.mock import patch, MagicMock
from backup import (
    BackupManager, BackupConfig, BackupResult,
    BackupStatus, BackupType, get_backup_manager
)


class TestBackupConfig(unittest.TestCase):
    """Testes para BackupConfig."""
    
    def test_default_config(self):
        """Testa configuração padrão."""
        config = BackupConfig(
            name="test",
            source_path="/tmp/test.db",
            backup_dir="/tmp/backups"
        )
        
        self.assertEqual(config.name, "test")
        self.assertEqual(config.backup_type, BackupType.FULL)
        self.assertTrue(config.compress)
        self.assertEqual(config.retention_days, 30)
        self.assertEqual(config.max_backups, 10)
        self.assertTrue(config.verify_after_backup)
        self.assertTrue(config.enabled)
    
    def test_to_dict(self):
        """Testa serialização para dict."""
        config = BackupConfig(
            name="test",
            source_path="/tmp/test.db",
            backup_dir="/tmp/backups",
            backup_type=BackupType.SNAPSHOT,
            compress=False,
            retention_days=7
        )
        
        d = config.to_dict()
        self.assertEqual(d["name"], "test")
        self.assertEqual(d["backup_type"], "snapshot")
        self.assertFalse(d["compress"])
        self.assertEqual(d["retention_days"], 7)


class TestBackupResult(unittest.TestCase):
    """Testes para BackupResult."""
    
    def test_to_dict(self):
        """Testa serialização para dict."""
        result = BackupResult(
            backup_id="test_20260318_120000",
            backup_type=BackupType.FULL,
            status=BackupStatus.COMPLETED,
            source_path="/tmp/test.db",
            backup_path="/tmp/backups/test_20260318_120000.db.gz",
            started_at=1710753600.0,
            finished_at=1710753601.5,
            duration_ms=1500.0,
            source_size_bytes=1024000,
            backup_size_bytes=512000,
            compression_ratio=0.5,
            checksum_sha256="abc123"
        )
        
        d = result.to_dict()
        self.assertEqual(d["backup_id"], "test_20260318_120000")
        self.assertEqual(d["status"], "completed")
        self.assertEqual(d["source_size_bytes"], 1024000)
        self.assertEqual(d["compression_ratio"], 0.5)


class TestBackupManager(unittest.TestCase):
    """Testes para BackupManager."""
    
    def setUp(self):
        """Setup para cada teste."""
        BackupManager.reset()
        self.manager = BackupManager()
        
        # Criar diretório temporário
        self.temp_dir = tempfile.mkdtemp()
        self.backup_dir = os.path.join(self.temp_dir, "backups")
        os.makedirs(self.backup_dir, exist_ok=True)
        
        # Criar banco SQLite de teste
        self.db_path = os.path.join(self.temp_dir, "test.db")
        self._create_test_db(self.db_path)
    
    def tearDown(self):
        """Cleanup após cada teste."""
        BackupManager.reset()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def _create_test_db(self, path: str):
        """Cria um banco SQLite de teste."""
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE test_data (
                id INTEGER PRIMARY KEY,
                name TEXT,
                value INTEGER,
                timestamp REAL
            )
        """)
        
        for i in range(100):
            cursor.execute(
                "INSERT INTO test_data (name, value, timestamp) VALUES (?, ?, ?)",
                (f"item_{i}", i * 10, time.time())
            )
        
        conn.commit()
        conn.close()
    
    def test_singleton(self):
        """Testa padrão singleton."""
        manager1 = BackupManager()
        manager2 = BackupManager()
        self.assertIs(manager1, manager2)
    
    def test_get_instance(self):
        """Testa get_instance."""
        manager = BackupManager.get_instance()
        self.assertIsInstance(manager, BackupManager)
    
    def test_reset(self):
        """Testa reset do singleton."""
        manager1 = BackupManager()
        BackupManager.reset()
        manager2 = BackupManager()
        self.assertIsNot(manager1, manager2)
    
    def test_add_config(self):
        """Testa adição de configuração."""
        config = BackupConfig(
            name="test_db",
            source_path=self.db_path,
            backup_dir=self.backup_dir
        )
        
        result = self.manager.add_config(config)
        self.assertTrue(result)
        
        retrieved = self.manager.get_config("test_db")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, "test_db")
    
    def test_add_duplicate_config(self):
        """Testa adição de configuração duplicada."""
        config = BackupConfig(
            name="test_db",
            source_path=self.db_path,
            backup_dir=self.backup_dir
        )
        
        self.manager.add_config(config)
        result = self.manager.add_config(config)
        self.assertFalse(result)
    
    def test_remove_config(self):
        """Testa remoção de configuração."""
        config = BackupConfig(
            name="test_db",
            source_path=self.db_path,
            backup_dir=self.backup_dir
        )
        
        self.manager.add_config(config)
        result = self.manager.remove_config("test_db")
        self.assertTrue(result)
        
        retrieved = self.manager.get_config("test_db")
        self.assertIsNone(retrieved)
    
    def test_remove_nonexistent_config(self):
        """Testa remoção de configuração inexistente."""
        result = self.manager.remove_config("nonexistent")
        self.assertFalse(result)
    
    def test_get_all_configs(self):
        """Testa listagem de todas as configurações."""
        config1 = BackupConfig(name="db1", source_path="/tmp/db1.db", backup_dir="/tmp/backups")
        config2 = BackupConfig(name="db2", source_path="/tmp/db2.db", backup_dir="/tmp/backups")
        
        self.manager.add_config(config1)
        self.manager.add_config(config2)
        
        configs = self.manager.get_all_configs()
        self.assertEqual(len(configs), 2)
    
    def test_backup_full(self):
        """Testa backup full."""
        config = BackupConfig(
            name="test_db",
            source_path=self.db_path,
            backup_dir=self.backup_dir,
            compress=True,
            verify_after_backup=True
        )
        
        self.manager.add_config(config)
        result = self.manager.backup("test_db")
        
        self.assertEqual(result.status, BackupStatus.VERIFIED)
        self.assertTrue(os.path.exists(result.backup_path))
        self.assertGreater(result.source_size_bytes, 0)
        self.assertGreater(result.backup_size_bytes, 0)
        self.assertLess(result.compression_ratio, 1.0)  # Comprimido deve ser menor
        self.assertNotEqual(result.checksum_sha256, "")
    
    def test_backup_without_compression(self):
        """Testa backup sem compressão."""
        config = BackupConfig(
            name="test_db",
            source_path=self.db_path,
            backup_dir=self.backup_dir,
            compress=False,
            verify_after_backup=True
        )
        
        self.manager.add_config(config)
        result = self.manager.backup("test_db")
        
        self.assertEqual(result.status, BackupStatus.VERIFIED)
        self.assertTrue(result.backup_path.endswith(".db"))
        self.assertFalse(result.backup_path.endswith(".gz"))
    
    def test_backup_nonexistent_source(self):
        """Testa backup de arquivo inexistente."""
        config = BackupConfig(
            name="test_db",
            source_path="/tmp/nonexistent.db",
            backup_dir=self.backup_dir
        )
        
        self.manager.add_config(config)
        result = self.manager.backup("test_db")
        
        self.assertEqual(result.status, BackupStatus.FAILED)
        self.assertIn("not found", result.error_message)
    
    def test_backup_nonexistent_config(self):
        """Testa backup com config inexistente."""
        result = self.manager.backup("nonexistent")
        
        self.assertEqual(result.status, BackupStatus.FAILED)
        self.assertIn("not found", result.error_message)
    
    def test_backup_disabled_config(self):
        """Testa backup com config desabilitada."""
        config = BackupConfig(
            name="test_db",
            source_path=self.db_path,
            backup_dir=self.backup_dir,
            enabled=False
        )
        
        self.manager.add_config(config)
        result = self.manager.backup("test_db")
        
        self.assertEqual(result.status, BackupStatus.FAILED)
        self.assertIn("disabled", result.error_message)
    
    def test_backup_all(self):
        """Testa backup de todas as configurações."""
        # Criar segundo banco
        db2_path = os.path.join(self.temp_dir, "test2.db")
        self._create_test_db(db2_path)
        
        config1 = BackupConfig(name="db1", source_path=self.db_path, backup_dir=self.backup_dir)
        config2 = BackupConfig(name="db2", source_path=db2_path, backup_dir=self.backup_dir)
        config3 = BackupConfig(name="db3", source_path="/tmp/nonexistent.db", backup_dir=self.backup_dir, enabled=True)
        
        self.manager.add_config(config1)
        self.manager.add_config(config2)
        self.manager.add_config(config3)
        
        results = self.manager.backup_all()
        
        # db3 falha porque arquivo não existe
        self.assertEqual(len(results), 3)
        success_count = sum(1 for r in results if r.status in (BackupStatus.COMPLETED, BackupStatus.VERIFIED))
        self.assertEqual(success_count, 2)
    
    def test_restore(self):
        """Testa restauração de backup."""
        config = BackupConfig(
            name="test_db",
            source_path=self.db_path,
            backup_dir=self.backup_dir,
            compress=True
        )
        
        self.manager.add_config(config)
        backup_result = self.manager.backup("test_db")
        
        # Restaurar
        restore_path = os.path.join(self.temp_dir, "restored.db")
        success, error = self.manager.restore(backup_result.backup_path, restore_path)
        
        self.assertTrue(success)
        self.assertEqual(error, "")
        self.assertTrue(os.path.exists(restore_path))
        
        # Verificar dados restaurados
        conn = sqlite3.connect(restore_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM test_data")
        count = cursor.fetchone()[0]
        conn.close()
        
        self.assertEqual(count, 100)
    
    def test_restore_nonexistent_backup(self):
        """Testa restauração de backup inexistente."""
        success, error = self.manager.restore("/tmp/nonexistent.gz", "/tmp/restored.db")
        
        self.assertFalse(success)
        self.assertIn("not found", error)
    
    def test_verify_backup(self):
        """Testa verificação de backup."""
        config = BackupConfig(
            name="test_db",
            source_path=self.db_path,
            backup_dir=self.backup_dir,
            compress=True
        )
        
        self.manager.add_config(config)
        backup_result = self.manager.backup("test_db")
        
        # Verificar backup válido
        is_valid, error = self.manager.verify_backup(backup_result.backup_path)
        self.assertTrue(is_valid)
        self.assertEqual(error, "")
    
    def test_verify_nonexistent_backup(self):
        """Testa verificação de backup inexistente."""
        is_valid, error = self.manager.verify_backup("/tmp/nonexistent.gz")
        
        self.assertFalse(is_valid)
        self.assertIn("not found", error)
    
    def test_history(self):
        """Testa histórico de backups."""
        config = BackupConfig(
            name="test_db",
            source_path=self.db_path,
            backup_dir=self.backup_dir
        )
        
        self.manager.add_config(config)
        
        # Executar alguns backups
        for _ in range(3):
            self.manager.backup("test_db")
            time.sleep(0.1)
        
        history = self.manager.get_history()
        self.assertEqual(len(history), 3)
        
        # Ordenado por mais recente primeiro
        self.assertGreaterEqual(history[0]["started_at"], history[1]["started_at"])
    
    def test_history_filter_config(self):
        """Testa filtro de histórico por config."""
        db2_path = os.path.join(self.temp_dir, "test2.db")
        self._create_test_db(db2_path)
        
        config1 = BackupConfig(name="db1", source_path=self.db_path, backup_dir=self.backup_dir)
        config2 = BackupConfig(name="db2", source_path=db2_path, backup_dir=self.backup_dir)
        
        self.manager.add_config(config1)
        self.manager.add_config(config2)
        
        self.manager.backup("db1")
        self.manager.backup("db2")
        self.manager.backup("db1")
        
        history_db1 = self.manager.get_history(config_name="db1")
        self.assertEqual(len(history_db1), 2)
    
    def test_history_success_only(self):
        """Testa filtro de histórico apenas sucessos."""
        config = BackupConfig(
            name="test_db",
            source_path=self.db_path,
            backup_dir=self.backup_dir
        )
        
        self.manager.add_config(config)
        
        # Backup bem-sucedido
        self.manager.backup("test_db")
        
        # Backup falho (config desabilitada)
        config_bad = BackupConfig(
            name="bad_db",
            source_path=self.db_path,
            backup_dir=self.backup_dir,
            enabled=False
        )
        self.manager.add_config(config_bad)
        self.manager.backup("bad_db")
        
        all_history = self.manager.get_history()
        success_history = self.manager.get_history(success_only=True)
        
        self.assertGreater(len(all_history), len(success_history))
    
    def test_stats(self):
        """Testa estatísticas."""
        config = BackupConfig(
            name="test_db",
            source_path=self.db_path,
            backup_dir=self.backup_dir
        )
        
        self.manager.add_config(config)
        self.manager.backup("test_db")
        
        stats = self.manager.get_stats()
        
        self.assertEqual(stats["total_backups"], 1)
        self.assertEqual(stats["successful_backups"], 1)
        self.assertEqual(stats["failed_backups"], 0)
        self.assertEqual(stats["success_rate"], 100.0)
        self.assertGreater(stats["total_bytes_backed_up"], 0)
        self.assertIsNotNone(stats["last_backup_at"])
    
    def test_get_backup_list(self):
        """Testa listagem de arquivos de backup."""
        config = BackupConfig(
            name="test_db",
            source_path=self.db_path,
            backup_dir=self.backup_dir
        )
        
        self.manager.add_config(config)
        self.manager.backup("test_db")
        
        backups = self.manager.get_backup_list(self.backup_dir)
        self.assertGreater(len(backups), 0)
        self.assertIn("filename", backups[0])
        self.assertIn("size_bytes", backups[0])
        self.assertIn("is_compressed", backups[0])
    
    def test_cleanup_old_backups(self):
        """Testa limpeza de backups antigos."""
        config = BackupConfig(
            name="test_db",
            source_path=self.db_path,
            backup_dir=self.backup_dir,
            max_backups=2
        )
        
        self.manager.add_config(config)
        
        # Criar 3 backups
        for _ in range(3):
            self.manager.backup("test_db")
            time.sleep(0.1)
        
        # Deve manter apenas 2
        backups = self.manager.get_backup_list(self.backup_dir, "test_db")
        self.assertLessEqual(len(backups), 2)
    
    def test_generate_backup_id(self):
        """Testa geração de ID de backup."""
        backup_id = self.manager._generate_backup_id("test_db")
        
        self.assertTrue(backup_id.startswith("test_db_"))
        self.assertIn("_", backup_id)
    
    def test_calculate_checksum(self):
        """Testa cálculo de checksum."""
        # Criar arquivo temporário
        test_file = os.path.join(self.temp_dir, "test_file.txt")
        with open(test_file, 'w') as f:
            f.write("test content")
        
        checksum = self.manager._calculate_checksum(test_file, "sha256")
        
        self.assertEqual(len(checksum), 64)  # SHA256 = 64 hex chars
        
        # Mesmo arquivo deve ter mesmo checksum
        checksum2 = self.manager._calculate_checksum(test_file, "sha256")
        self.assertEqual(checksum, checksum2)
    
    def test_verify_sqlite_integrity(self):
        """Testa verificação de integridade SQLite."""
        is_valid, error = self.manager._verify_sqlite_integrity(self.db_path)
        
        self.assertTrue(is_valid)
        self.assertEqual(error, "")
    
    def test_verify_corrupted_db(self):
        """Testa verificação de banco corrompido."""
        # Criar arquivo corrompido
        corrupted_path = os.path.join(self.temp_dir, "corrupted.db")
        with open(corrupted_path, 'w') as f:
            f.write("this is not a sqlite database")
        
        is_valid, error = self.manager._verify_sqlite_integrity(corrupted_path)
        
        self.assertFalse(is_valid)
        self.assertNotEqual(error, "")


class TestBackupManagerEdgeCases(unittest.TestCase):
    """Testes de edge cases para BackupManager."""
    
    def setUp(self):
        BackupManager.reset()
        self.manager = BackupManager()
        self.temp_dir = tempfile.mkdtemp()
        self.backup_dir = os.path.join(self.temp_dir, "backups")
        os.makedirs(self.backup_dir, exist_ok=True)
        
        self.db_path = os.path.join(self.temp_dir, "test.db")
        conn = sqlite3.connect(self.db_path)
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
        conn.commit()
        conn.close()
    
    def tearDown(self):
        BackupManager.reset()
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
    
    def test_empty_database(self):
        """Testa backup de banco vazio."""
        empty_db = os.path.join(self.temp_dir, "empty.db")
        conn = sqlite3.connect(empty_db)
        conn.close()
        
        config = BackupConfig(
            name="empty",
            source_path=empty_db,
            backup_dir=self.backup_dir
        )
        
        self.manager.add_config(config)
        result = self.manager.backup("empty")
        
        self.assertIn(result.status, (BackupStatus.COMPLETED, BackupStatus.VERIFIED))
    
    def test_large_compression_ratio(self):
        """Testa compressão de banco com dados repetitivos."""
        large_db = os.path.join(self.temp_dir, "large.db")
        conn = sqlite3.connect(large_db)
        conn.execute("CREATE TABLE data (content TEXT)")
        
        # Dados muito repetitivos (alta compressão)
        for _ in range(1000):
            conn.execute("INSERT INTO data VALUES (?)", ("A" * 1000,))
        
        conn.commit()
        conn.close()
        
        config = BackupConfig(
            name="large",
            source_path=large_db,
            backup_dir=self.backup_dir,
            compress=True
        )
        
        self.manager.add_config(config)
        result = self.manager.backup("large")
        
        self.assertIn(result.status, (BackupStatus.COMPLETED, BackupStatus.VERIFIED))
        self.assertLess(result.compression_ratio, 0.1)  # >90% compressão
    
    def test_backup_without_verify(self):
        """Testa backup sem verificação."""
        config = BackupConfig(
            name="test",
            source_path=self.db_path,
            backup_dir=self.backup_dir,
            verify_after_backup=False
        )
        
        self.manager.add_config(config)
        result = self.manager.backup("test")
        
        self.assertEqual(result.status, BackupStatus.COMPLETED)
    
    def test_human_readable_size(self):
        """Testa formatação de tamanho legível."""
        self.assertEqual(self.manager._human_readable_size(500), "500.0 B")
        self.assertEqual(self.manager._human_readable_size(1024), "1.0 KB")
        self.assertEqual(self.manager._human_readable_size(1048576), "1.0 MB")
        self.assertEqual(self.manager._human_readable_size(1073741824), "1.0 GB")


class TestGetBackupManager(unittest.TestCase):
    """Testes para função get_backup_manager."""
    
    def setUp(self):
        BackupManager.reset()
    
    def tearDown(self):
        BackupManager.reset()
    
    def test_returns_manager(self):
        """Testa que retorna instância de BackupManager."""
        manager = get_backup_manager()
        self.assertIsInstance(manager, BackupManager)
    
    def test_returns_same_instance(self):
        """Testa que retorna mesma instância."""
        manager1 = get_backup_manager()
        manager2 = get_backup_manager()
        self.assertIs(manager1, manager2)


if __name__ == '__main__':
    unittest.main()
