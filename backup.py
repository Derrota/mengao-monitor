"""
Mengão Monitor v3.14 - Backup System
Sistema de backup automático para SQLite com compressão, rotação e verificação.

Zero dependências externas — apenas stdlib.
"""

import os
import time
import shutil
import sqlite3
import hashlib
import threading
import gzip
import json
from dataclasses import dataclass, field
from typing import Optional, Callable, Dict, List, Any, Tuple
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict


class BackupStatus(Enum):
    """Status de um backup."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    VERIFIED = "verified"
    CORRUPTED = "corrupted"


class BackupType(Enum):
    """Tipos de backup."""
    FULL = "full"           # Backup completo do banco
    INCREMENTAL = "incremental"  # Apenas mudanças desde último backup
    SNAPSHOT = "snapshot"   # Snapshot rápido (cópia direta)


@dataclass
class BackupResult:
    """Resultado de uma operação de backup."""
    backup_id: str
    backup_type: BackupType
    status: BackupStatus
    source_path: str
    backup_path: str
    started_at: float
    finished_at: float
    duration_ms: float
    source_size_bytes: int = 0
    backup_size_bytes: int = 0
    compression_ratio: float = 0.0
    checksum_sha256: str = ""
    error_message: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "backup_id": self.backup_id,
            "backup_type": self.backup_type.value,
            "status": self.status.value,
            "source_path": self.source_path,
            "backup_path": self.backup_path,
            "started_at": datetime.fromtimestamp(self.started_at).isoformat(),
            "finished_at": datetime.fromtimestamp(self.finished_at).isoformat(),
            "duration_ms": round(self.duration_ms, 2),
            "source_size_bytes": self.source_size_bytes,
            "backup_size_bytes": self.backup_size_bytes,
            "compression_ratio": round(self.compression_ratio, 3),
            "checksum_sha256": self.checksum_sha256,
            "error_message": self.error_message,
            "metadata": self.metadata
        }


@dataclass
class BackupConfig:
    """Configuração de backup."""
    name: str
    source_path: str
    backup_dir: str
    backup_type: BackupType = BackupType.FULL
    compress: bool = True
    retention_days: int = 30
    max_backups: int = 10
    verify_after_backup: bool = True
    checksum_algorithm: str = "sha256"
    schedule_cron: Optional[str] = None
    enabled: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "source_path": self.source_path,
            "backup_dir": self.backup_dir,
            "backup_type": self.backup_type.value,
            "compress": self.compress,
            "retention_days": self.retention_days,
            "max_backups": self.max_backups,
            "verify_after_backup": self.verify_after_backup,
            "checksum_algorithm": self.checksum_algorithm,
            "schedule_cron": self.schedule_cron,
            "enabled": self.enabled
        }


class BackupManager:
    """
    Gerenciador de backups automáticos para SQLite.
    
    Features:
    - Backup full, incremental e snapshot
    - Compressão gzip automática
    - Verificação de integridade (checksum)
    - Rotação automática (retenção por dias e quantidade)
    - Histórico de backups
    - Thread-safe
    - Singleton pattern
    """
    
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._configs: Dict[str, BackupConfig] = {}
        self._history: List[BackupResult] = []
        self._history_lock = threading.RLock()
        self._stats = {
            "total_backups": 0,
            "successful_backups": 0,
            "failed_backups": 0,
            "total_bytes_backed_up": 0,
            "total_bytes_compressed": 0,
            "last_backup_at": None,
            "configs_created": 0
        }
        self._initialized = True
    
    @classmethod
    def get_instance(cls) -> 'BackupManager':
        """Retorna a instância singleton."""
        return cls()
    
    @classmethod
    def reset(cls):
        """Reseta a instância singleton (para testes)."""
        with cls._lock:
            cls._instance = None
    
    def add_config(self, config: BackupConfig) -> bool:
        """Adiciona uma configuração de backup."""
        with self._lock:
            if config.name in self._configs:
                return False
            self._configs[config.name] = config
            self._stats["configs_created"] += 1
            return True
    
    def remove_config(self, name: str) -> bool:
        """Remove uma configuração de backup."""
        with self._lock:
            if name not in self._configs:
                return False
            del self._configs[name]
            return True
    
    def get_config(self, name: str) -> Optional[BackupConfig]:
        """Retorna uma configuração de backup."""
        return self._configs.get(name)
    
    def get_all_configs(self) -> List[Dict[str, Any]]:
        """Retorna todas as configurações."""
        return [config.to_dict() for config in self._configs.values()]
    
    def _generate_backup_id(self, config_name: str) -> str:
        """Gera um ID único para o backup."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{config_name}_{timestamp}"
    
    def _calculate_checksum(self, filepath: str, algorithm: str = "sha256") -> str:
        """Calcula checksum de um arquivo."""
        hash_func = hashlib.sha256() if algorithm == "sha256" else hashlib.md5()
        
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()
    
    def _verify_sqlite_integrity(self, db_path: str) -> Tuple[bool, str]:
        """
        Verifica integridade de um banco SQLite.
        
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        """
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # PRAGMA integrity_check
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()
            
            conn.close()
            
            if result and result[0] == "ok":
                return True, ""
            else:
                return False, f"Integrity check failed: {result[0] if result else 'unknown'}"
        
        except sqlite3.Error as e:
            return False, f"SQLite error: {str(e)}"
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"
    
    def _compress_file(self, source_path: str, dest_path: str) -> int:
        """
        Comprime um arquivo usando gzip.
        
        Returns:
            int: Tamanho do arquivo comprimido em bytes
        """
        with open(source_path, 'rb') as f_in:
            with gzip.open(dest_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        return os.path.getsize(dest_path)
    
    def _decompress_file(self, source_path: str, dest_path: str) -> int:
        """
        Descomprime um arquivo gzip.
        
        Returns:
            int: Tamanho do arquivo descomprimido em bytes
        """
        with gzip.open(source_path, 'rb') as f_in:
            with open(dest_path, 'wb') as f_out:
                shutil.copyfileobj(f_in, f_out)
        
        return os.path.getsize(dest_path)
    
    def _ensure_backup_dir(self, backup_dir: str):
        """Garante que o diretório de backup existe."""
        os.makedirs(backup_dir, exist_ok=True)
    
    def _get_backup_files(self, backup_dir: str, config_name: str) -> List[Tuple[str, float]]:
        """
        Retorna lista de arquivos de backup para uma config, ordenados por data.
        
        Returns:
            List[Tuple[str, float]]: Lista de (filepath, mtime)
        """
        files = []
        prefix = f"{config_name}_"
        
        for filename in os.listdir(backup_dir):
            if filename.startswith(prefix):
                filepath = os.path.join(backup_dir, filename)
                if os.path.isfile(filepath):
                    mtime = os.path.getmtime(filepath)
                    files.append((filepath, mtime))
        
        # Ordenar por mtime (mais antigo primeiro)
        files.sort(key=lambda x: x[1])
        return files
    
    def _cleanup_old_backups(self, config: BackupConfig):
        """Remove backups antigos baseado na política de retenção."""
        backup_files = self._get_backup_files(config.backup_dir, config.name)
        
        now = time.time()
        retention_seconds = config.retention_days * 86400
        
        removed_count = 0
        
        # Remover por idade
        for filepath, mtime in backup_files:
            age = now - mtime
            if age > retention_seconds:
                try:
                    os.remove(filepath)
                    removed_count += 1
                except OSError:
                    pass
        
        # Remover por quantidade (mantém os mais recentes)
        backup_files = self._get_backup_files(config.backup_dir, config.name)
        if len(backup_files) > config.max_backups:
            to_remove = backup_files[:len(backup_files) - config.max_backups]
            for filepath, _ in to_remove:
                try:
                    os.remove(filepath)
                    removed_count += 1
                except OSError:
                    pass
        
        return removed_count
    
    def backup(self, config_name: str) -> BackupResult:
        """
        Executa um backup para a configuração especificada.
        
        Args:
            config_name: Nome da configuração de backup
            
        Returns:
            BackupResult: Resultado da operação
        """
        config = self._configs.get(config_name)
        if not config:
            return BackupResult(
                backup_id="",
                backup_type=BackupType.FULL,
                status=BackupStatus.FAILED,
                source_path="",
                backup_path="",
                started_at=time.time(),
                finished_at=time.time(),
                duration_ms=0,
                error_message=f"Config not found: {config_name}"
            )
        
        if not config.enabled:
            result = BackupResult(
                backup_id="",
                backup_type=config.backup_type,
                status=BackupStatus.FAILED,
                source_path=config.source_path,
                backup_path="",
                started_at=time.time(),
                finished_at=time.time(),
                duration_ms=0,
                error_message=f"Config disabled: {config_name}"
            )
            self._stats["total_backups"] += 1
            self._stats["failed_backups"] += 1
            with self._history_lock:
                self._history.append(result)
            return result
        
        if not os.path.exists(config.source_path):
            result = BackupResult(
                backup_id="",
                backup_type=config.backup_type,
                status=BackupStatus.FAILED,
                source_path=config.source_path,
                backup_path="",
                started_at=time.time(),
                finished_at=time.time(),
                duration_ms=0,
                error_message=f"Source file not found: {config.source_path}"
            )
            self._stats["total_backups"] += 1
            self._stats["failed_backups"] += 1
            with self._history_lock:
                self._history.append(result)
            return result
        
        started_at = time.time()
        backup_id = self._generate_backup_id(config_name)
        
        try:
            # Garantir diretório de backup
            self._ensure_backup_dir(config.backup_dir)
            
            # Determinar caminho do backup
            backup_filename = f"{backup_id}.db"
            if config.compress:
                backup_filename += ".gz"
            backup_path = os.path.join(config.backup_dir, backup_filename)
            
            # Tamanho do arquivo original
            source_size = os.path.getsize(config.source_path)
            
            # Verificar integridade do source antes do backup
            if config.backup_type == BackupType.FULL:
                is_valid, error = self._verify_sqlite_integrity(config.source_path)
                if not is_valid:
                    return BackupResult(
                        backup_id=backup_id,
                        backup_type=config.backup_type,
                        status=BackupStatus.FAILED,
                        source_path=config.source_path,
                        backup_path=backup_path,
                        started_at=started_at,
                        finished_at=time.time(),
                        duration_ms=(time.time() - started_at) * 1000,
                        source_size_bytes=source_size,
                        error_message=f"Source integrity check failed: {error}"
                    )
            
            # Executar backup
            if config.compress:
                backup_size = self._compress_file(config.source_path, backup_path)
            else:
                shutil.copy2(config.source_path, backup_path)
                backup_size = os.path.getsize(backup_path)
            
            # Calcular checksum
            checksum = self._calculate_checksum(backup_path, config.checksum_algorithm)
            
            # Calcular ratio de compressão
            compression_ratio = backup_size / source_size if source_size > 0 else 1.0
            
            # Verificar backup se configurado
            status = BackupStatus.COMPLETED
            if config.verify_after_backup and config.compress:
                # Descomprimir temporariamente para verificar
                temp_path = backup_path + ".verify"
                try:
                    self._decompress_file(backup_path, temp_path)
                    is_valid, error = self._verify_sqlite_integrity(temp_path)
                    if is_valid:
                        status = BackupStatus.VERIFIED
                    else:
                        status = BackupStatus.CORRUPTED
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
            elif config.verify_after_backup:
                is_valid, error = self._verify_sqlite_integrity(backup_path)
                if is_valid:
                    status = BackupStatus.VERIFIED
                else:
                    status = BackupStatus.CORRUPTED
            
            finished_at = time.time()
            duration_ms = (finished_at - started_at) * 1000
            
            result = BackupResult(
                backup_id=backup_id,
                backup_type=config.backup_type,
                status=status,
                source_path=config.source_path,
                backup_path=backup_path,
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
                source_size_bytes=source_size,
                backup_size_bytes=backup_size,
                compression_ratio=compression_ratio,
                checksum_sha256=checksum,
                metadata={
                    "config_name": config_name,
                    "compressed": config.compress,
                    "verified": config.verify_after_backup
                }
            )
            
            # Atualizar stats
            self._stats["total_backups"] += 1
            if status in (BackupStatus.COMPLETED, BackupStatus.VERIFIED):
                self._stats["successful_backups"] += 1
                self._stats["total_bytes_backed_up"] += source_size
                self._stats["total_bytes_compressed"] += backup_size
            else:
                self._stats["failed_backups"] += 1
            
            self._stats["last_backup_at"] = finished_at
            
            # Adicionar ao histórico
            with self._history_lock:
                self._history.append(result)
                # Manter apenas últimos 1000
                if len(self._history) > 1000:
                    self._history = self._history[-1000:]
            
            # Cleanup de backups antigos
            self._cleanup_old_backups(config)
            
            return result
        
        except Exception as e:
            finished_at = time.time()
            duration_ms = (finished_at - started_at) * 1000
            
            result = BackupResult(
                backup_id=backup_id,
                backup_type=config.backup_type,
                status=BackupStatus.FAILED,
                source_path=config.source_path,
                backup_path="",
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
                source_size_bytes=os.path.getsize(config.source_path) if os.path.exists(config.source_path) else 0,
                error_message=str(e)
            )
            
            self._stats["total_backups"] += 1
            self._stats["failed_backups"] += 1
            
            with self._history_lock:
                self._history.append(result)
            
            return result
    
    def backup_all(self) -> List[BackupResult]:
        """Executa backup de todas as configurações habilitadas."""
        results = []
        
        for config_name in list(self._configs.keys()):
            config = self._configs[config_name]
            if config.enabled:
                result = self.backup(config_name)
                results.append(result)
        
        return results
    
    def restore(self, backup_path: str, restore_path: str, 
                verify: bool = True) -> Tuple[bool, str]:
        """
        Restaura um backup.
        
        Args:
            backup_path: Caminho do arquivo de backup
            restore_path: Caminho onde restaurar
            verify: Se deve verificar integridade após restaurar
            
        Returns:
            Tuple[bool, str]: (success, error_message)
        """
        if not os.path.exists(backup_path):
            return False, f"Backup file not found: {backup_path}"
        
        try:
            # Verificar se é comprimido
            is_compressed = backup_path.endswith('.gz')
            
            if is_compressed:
                # Descomprimir
                self._decompress_file(backup_path, restore_path)
            else:
                # Cópia direta
                shutil.copy2(backup_path, restore_path)
            
            # Verificar integridade se solicitado
            if verify:
                is_valid, error = self._verify_sqlite_integrity(restore_path)
                if not is_valid:
                    os.remove(restore_path)
                    return False, f"Restored database integrity check failed: {error}"
            
            return True, ""
        
        except Exception as e:
            return False, f"Restore failed: {str(e)}"
    
    def verify_backup(self, backup_path: str) -> Tuple[bool, str]:
        """
        Verifica integridade de um backup.
        
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        """
        if not os.path.exists(backup_path):
            return False, f"Backup file not found: {backup_path}"
        
        try:
            is_compressed = backup_path.endswith('.gz')
            
            if is_compressed:
                # Descomprimir temporariamente
                temp_path = backup_path + ".verify"
                try:
                    self._decompress_file(backup_path, temp_path)
                    return self._verify_sqlite_integrity(temp_path)
                finally:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
            else:
                return self._verify_sqlite_integrity(backup_path)
        
        except Exception as e:
            return False, f"Verification failed: {str(e)}"
    
    def get_history(self, config_name: Optional[str] = None, 
                    limit: int = 50, success_only: bool = False) -> List[Dict[str, Any]]:
        """Retorna histórico de backups."""
        with self._history_lock:
            history = self._history.copy()
        
        # Filtrar por config_name
        if config_name:
            history = [r for r in history if r.metadata.get("config_name") == config_name]
        
        # Filtrar por sucesso
        if success_only:
            history = [r for r in history if r.status in (BackupStatus.COMPLETED, BackupStatus.VERIFIED)]
        
        # Ordenar por started_at (mais recente primeiro)
        history.sort(key=lambda r: r.started_at, reverse=True)
        
        # Limitar
        history = history[:limit]
        
        return [r.to_dict() for r in history]
    
    def get_stats(self) -> Dict[str, Any]:
        """Retorna estatísticas do gerenciador."""
        with self._lock:
            stats = self._stats.copy()
            stats["configs_count"] = len(self._configs)
            stats["history_size"] = len(self._history)
            
            # Calcular success rate
            if stats["total_backups"] > 0:
                stats["success_rate"] = round(
                    (stats["successful_backups"] / stats["total_backups"]) * 100, 2
                )
            else:
                stats["success_rate"] = 0.0
            
            # Calcular compressão média
            if stats["total_bytes_backed_up"] > 0:
                stats["avg_compression_ratio"] = round(
                    stats["total_bytes_compressed"] / stats["total_bytes_backed_up"], 3
                )
            else:
                stats["avg_compression_ratio"] = 0.0
            
            # Converter timestamps
            if stats["last_backup_at"]:
                stats["last_backup_at"] = datetime.fromtimestamp(stats["last_backup_at"]).isoformat()
            
            return stats
    
    def get_backup_list(self, backup_dir: str, config_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lista arquivos de backup em um diretório.
        
        Returns:
            List[Dict]: Lista de informações de backup
        """
        if not os.path.exists(backup_dir):
            return []
        
        backups = []
        
        for filename in os.listdir(backup_dir):
            filepath = os.path.join(backup_dir, filename)
            
            if not os.path.isfile(filepath):
                continue
            
            # Filtrar por config_name se especificado
            if config_name and not filename.startswith(f"{config_name}_"):
                continue
            
            # Extrair informações do nome do arquivo
            # Formato: {config_name}_{YYYYMMDD_HHMMSS}.db[.gz]
            parts = filename.replace('.db.gz', '').replace('.db', '').split('_')
            
            if len(parts) >= 3:
                config_from_name = '_'.join(parts[:-2])
                date_str = parts[-2]
                time_str = parts[-1]
            else:
                config_from_name = "unknown"
                date_str = "unknown"
                time_str = "unknown"
            
            stat = os.stat(filepath)
            
            backups.append({
                "filename": filename,
                "filepath": filepath,
                "config_name": config_from_name,
                "date": date_str,
                "time": time_str,
                "size_bytes": stat.st_size,
                "size_human": self._human_readable_size(stat.st_size),
                "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "is_compressed": filename.endswith('.gz')
            })
        
        # Ordenar por data de criação (mais recente primeiro)
        backups.sort(key=lambda x: x["created_at"], reverse=True)
        
        return backups
    
    def _human_readable_size(self, size_bytes: int) -> str:
        """Converte bytes para formato legível."""
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} TB"


# Instância global
_backup_manager = None


def get_backup_manager() -> BackupManager:
    """Retorna a instância global do BackupManager."""
    global _backup_manager
    if _backup_manager is None:
        _backup_manager = BackupManager.get_instance()
    return _backup_manager
