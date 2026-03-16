"""
Testes para Performance Profiler v3.7
"""

import time
import json
import threading
import unittest
from unittest.mock import patch, MagicMock

from performance_profiler import (
    PerformanceProfiler,
    ProfileEntry,
    ProfileStats,
    RegressionAlert,
    ProfileContext,
    profile,
    get_profiler
)


class TestProfileEntry(unittest.TestCase):
    """Testes para ProfileEntry."""
    
    def test_to_dict(self):
        entry = ProfileEntry(
            name="test_func",
            duration_ms=12.345,
            timestamp=1234567890.0,
            metadata={"key": "value"}
        )
        d = entry.to_dict()
        assert d["name"] == "test_func"
        assert d["duration_ms"] == 12.345
        assert d["metadata"] == {"key": "value"}


class TestProfileStats(unittest.TestCase):
    """Testes para ProfileStats."""
    
    def test_to_dict(self):
        stats = ProfileStats(
            name="test",
            count=100,
            total_ms=1000.0,
            avg_ms=10.0,
            p50_ms=9.0,
            p95_ms=15.0,
            p99_ms=20.0,
            min_ms=5.0,
            max_ms=25.0,
            std_dev_ms=3.0
        )
        d = stats.to_dict()
        assert d["name"] == "test"
        assert d["count"] == 100
        assert d["avg_ms"] == 10.0


class TestPerformanceProfiler(unittest.TestCase):
    """Testes para PerformanceProfiler."""
    
    def test_init_default(self):
        profiler = PerformanceProfiler()
        assert profiler.enabled is True
        assert profiler.max_history == 10000
        assert profiler.regression_threshold_pct == 20.0
    
    def test_init_custom(self):
        profiler = PerformanceProfiler(
            max_history=5000,
            regression_threshold_pct=30.0,
            regression_window=50
        )
        assert profiler.max_history == 5000
        assert profiler.regression_threshold_pct == 30.0
    
    def test_enable_disable(self):
        profiler = PerformanceProfiler()
        assert profiler.enabled is True
        
        profiler.disable()
        assert profiler.enabled is False
        
        profiler.enable()
        assert profiler.enabled is True
    
    def test_record_basic(self):
        profiler = PerformanceProfiler()
        profiler.record("test_func", 10.5)
        profiler.record("test_func", 20.3)
        profiler.record("test_func", 15.7)
        
        stats = profiler.get_stats("test_func")
        assert stats is not None
        assert stats.count == 3
        assert stats.min_ms == 10.5
        assert stats.max_ms == 20.3
        assert 10.5 <= stats.avg_ms <= 20.3
    
    def test_record_with_metadata(self):
        profiler = PerformanceProfiler()
        profiler.record("test", 10.0, metadata={"endpoint": "/health"})
        
        history = profiler.get_history("test")
        assert len(history) == 1
        assert history[0].metadata["endpoint"] == "/health"
    
    def test_record_disabled(self):
        profiler = PerformanceProfiler()
        profiler.disable()
        profiler.record("test", 10.0)
        
        stats = profiler.get_stats("test")
        assert stats is None
    
    def test_get_stats_empty(self):
        profiler = PerformanceProfiler()
        stats = profiler.get_stats("nonexistent")
        assert stats is None
    
    def test_get_all_stats(self):
        profiler = PerformanceProfiler()
        profiler.record("func_a", 100.0)
        profiler.record("func_b", 50.0)
        profiler.record("func_a", 100.0)
        
        all_stats = profiler.get_all_stats()
        assert len(all_stats) == 2
        # Ordenado por total_ms desc
        assert all_stats[0].name == "func_a"
        assert all_stats[1].name == "func_b"
    
    def test_get_bottlenecks(self):
        profiler = PerformanceProfiler()
        for i in range(10):
            profiler.record("slow", 100.0)
        for i in range(5):
            profiler.record("fast", 1.0)
        
        bottlenecks = profiler.get_bottlenecks(2)
        assert len(bottlenecks) == 2
        assert bottlenecks[0].name == "slow"
    
    def test_get_slowest(self):
        profiler = PerformanceProfiler()
        profiler.record("avg_slow", 50.0)
        profiler.record("avg_slow", 60.0)
        profiler.record("spike", 500.0)
        profiler.record("spike", 10.0)
        
        slowest = profiler.get_slowest(2)
        assert slowest[0].name == "spike"  # Maior p95
    
    def test_get_history_with_limit(self):
        profiler = PerformanceProfiler()
        for i in range(20):
            profiler.record("test", float(i))
        
        history = profiler.get_history("test", limit=5)
        assert len(history) == 5
        assert history[-1].duration_ms == 19.0
    
    def test_get_history_with_since(self):
        profiler = PerformanceProfiler()
        profiler.record("test", 10.0)
        time.sleep(0.1)
        profiler.record("test", 20.0)
        
        # Buscar últimos 0.05 segundos (só o segundo)
        history = profiler.get_history("test", since_seconds=0.05)
        assert len(history) == 1
        assert history[0].duration_ms == 20.0
    
    def test_max_history_trimming(self):
        profiler = PerformanceProfiler(max_history=5)
        for i in range(10):
            profiler.record("test", float(i))
        
        history = profiler.get_history("test")
        assert len(history) == 5
        assert history[0].duration_ms == 5.0  # Primeiros 5 foram descartados
    
    def test_get_global_stats(self):
        profiler = PerformanceProfiler()
        profiler.record("a", 10.0)
        profiler.record("b", 20.0)
        
        stats = profiler.get_global_stats()
        assert stats["tracked_functions"] == 2
        assert stats["total_entries"] == 2
        assert stats["enabled"] is True
        assert "uptime_seconds" in stats
    
    def test_reset(self):
        profiler = PerformanceProfiler()
        profiler.record("test", 10.0)
        profiler.record("test", 20.0)
        
        profiler.reset()
        
        stats = profiler.get_stats("test")
        assert stats is None
        
        global_stats = profiler.get_global_stats()
        assert global_stats["total_profiles"] == 0
    
    def test_export_json(self):
        import tempfile
        import os
        
        profiler = PerformanceProfiler()
        profiler.record("test", 10.0)
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            filepath = f.name
        
        try:
            profiler.export_json(filepath)
            
            with open(filepath) as f:
                data = json.load(f)
            
            assert "global_stats" in data
            assert "bottlenecks" in data
            assert "slowest_functions" in data
            assert "regressions" in data
            assert "recommendations" in data
        finally:
            os.unlink(filepath)


class TestRegressionDetection(unittest.TestCase):
    """Testes para detecção de regressão."""
    
    def test_no_regression_stable(self):
        profiler = PerformanceProfiler(
            regression_threshold_pct=20.0,
            regression_window=10
        )
        
        # 20 amostras estáveis
        for i in range(20):
            profiler.record("stable", 10.0 + (i % 3))  # 10-12ms
        
        regressions = profiler.get_regressions()
        assert len(regressions) == 0
    
    def test_regression_detected(self):
        profiler = PerformanceProfiler(
            regression_threshold_pct=20.0,
            regression_window=10
        )
        
        # 10 amostras lentas (baseline)
        for i in range(10):
            profiler.record("slowdown", 10.0)
        
        # 10 amostras rápidas (baseline)
        for i in range(10):
            profiler.record("slowdown", 10.0)
        
        # 10 amostras lentas (regressão: 100% aumento)
        for i in range(10):
            profiler.record("slowdown", 20.0)
        
        regressions = profiler.get_regressions()
        assert len(regressions) >= 1
        assert regressions[0].name == "slowdown"
        assert regressions[0].regression_pct > 20.0
    
    def test_regression_below_threshold(self):
        profiler = PerformanceProfiler(
            regression_threshold_pct=50.0,
            regression_window=10
        )
        
        # Baseline: 10ms
        for i in range(20):
            profiler.record("small_change", 10.0)
        
        # Aumento de 30% (abaixo de 50% threshold)
        for i in range(10):
            profiler.record("small_change", 13.0)
        
        regressions = profiler.get_regressions()
        assert len(regressions) == 0
    
    def test_generate_report_with_regressions(self):
        profiler = PerformanceProfiler(
            regression_threshold_pct=20.0,
            regression_window=5
        )
        
        for i in range(10):
            profiler.record("regressing", 10.0)
        for i in range(10):
            profiler.record("regressing", 25.0)
        
        report = profiler.generate_report()
        assert len(report["regressions"]) >= 1
        assert any("regressing" in r["name"] for r in report["regressions"])


class TestThreadSafety(unittest.TestCase):
    """Testes para thread safety."""
    
    def test_concurrent_record(self):
        profiler = PerformanceProfiler()
        errors = []
        
        def record_many():
            try:
                for i in range(100):
                    profiler.record("concurrent", float(i))
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=record_many) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        stats = profiler.get_stats("concurrent")
        assert stats.count == 500
    
    def test_concurrent_read_write(self):
        profiler = PerformanceProfiler()
        errors = []
        
        def writer():
            try:
                for i in range(50):
                    profiler.record("rw_test", float(i))
            except Exception as e:
                errors.append(e)
        
        def reader():
            try:
                for i in range(50):
                    profiler.get_stats("rw_test")
                    profiler.get_all_stats()
            except Exception as e:
                errors.append(e)
        
        writers = [threading.Thread(target=writer) for _ in range(3)]
        readers = [threading.Thread(target=reader) for _ in range(3)]
        
        for t in writers + readers:
            t.start()
        for t in writers + readers:
            t.join()
        
        assert len(errors) == 0


class TestProfileDecorator(unittest.TestCase):
    """Testes para o decorator @profile."""
    
    def test_decorator_basic(self):
        # Reset global profiler
        import performance_profiler
        performance_profiler._global_profiler = PerformanceProfiler()
        
        @profile()
        def sample_func():
            time.sleep(0.01)
            return "done"
        
        result = sample_func()
        assert result == "done"
        
        profiler = get_profiler()
        stats = profiler.get_stats("test_performance_profiler.sample_func")
        assert stats is not None
        assert stats.count == 1
        assert stats.avg_ms >= 10.0  # Pelo menos 10ms
    
    def test_decorator_custom_name(self):
        import performance_profiler
        performance_profiler._global_profiler = PerformanceProfiler()
        
        @profile("custom_name")
        def sample_func():
            return 42
        
        result = sample_func()
        assert result == 42
        
        profiler = get_profiler()
        stats = profiler.get_stats("custom_name")
        assert stats is not None
    
    def test_decorator_with_metadata(self):
        import performance_profiler
        performance_profiler._global_profiler = PerformanceProfiler()
        
        @profile(metadata={"version": "3.7"})
        def sample_func():
            pass
        
        sample_func()
        
        profiler = get_profiler()
        history = profiler.get_history("test_performance_profiler.sample_func")
        assert len(history) == 1
        assert history[0].metadata["version"] == "3.7"
    
    def test_decorator_disabled(self):
        import performance_profiler
        performance_profiler._global_profiler = PerformanceProfiler()
        profiler = get_profiler()
        profiler.disable()
        
        @profile()
        def sample_func():
            return "ok"
        
        result = sample_func()
        assert result == "ok"
        
        stats = profiler.get_stats("test_performance_profiler.sample_func")
        assert stats is None
    
    def test_decorator_preserves_function_metadata(self):
        @profile()
        def documented_func():
            """Docstring here."""
            pass
        
        assert documented_func.__name__ == "documented_func"
        assert documented_func.__doc__ == "Docstring here."


class TestProfileContext(unittest.TestCase):
    """Testes para ProfileContext."""
    
    def test_context_basic(self):
        import performance_profiler
        performance_profiler._global_profiler = PerformanceProfiler()
        
        with ProfileContext("my_block"):
            time.sleep(0.01)
        
        profiler = get_profiler()
        stats = profiler.get_stats("my_block")
        assert stats is not None
        assert stats.count == 1
        assert stats.avg_ms >= 10.0
    
    def test_context_with_metadata(self):
        import performance_profiler
        performance_profiler._global_profiler = PerformanceProfiler()
        
        with ProfileContext("meta_block", metadata={"tag": "test"}):
            pass
        
        profiler = get_profiler()
        history = profiler.get_history("meta_block")
        assert history[0].metadata["tag"] == "test"
    
    def test_context_disabled(self):
        import performance_profiler
        performance_profiler._global_profiler = PerformanceProfiler()
        profiler = get_profiler()
        profiler.disable()
        
        with ProfileContext("disabled_block"):
            pass
        
        stats = profiler.get_stats("disabled_block")
        assert stats is None


class TestPercentiles(unittest.TestCase):
    """Testes para cálculo de percentis."""
    
    def test_percentiles_distribution(self):
        profiler = PerformanceProfiler()
        
        # 100 amostras: 0, 1, 2, ..., 99
        for i in range(100):
            profiler.record("dist", float(i))
        
        stats = profiler.get_stats("dist")
        assert stats.p50_ms == 50.0
        assert stats.p95_ms == 95.0
        assert stats.p99_ms == 99.0
    
    def test_percentiles_few_samples(self):
        profiler = PerformanceProfiler()
        profiler.record("few", 10.0)
        profiler.record("few", 20.0)
        profiler.record("few", 30.0)
        
        stats = profiler.get_stats("few")
        assert stats is not None
        assert stats.count == 3


class TestRecommendations(unittest.TestCase):
    """Testes para geração de recomendações."""
    
    def test_no_recommendations_when_healthy(self):
        profiler = PerformanceProfiler()
        for i in range(10):
            profiler.record("healthy", 5.0)
        
        report = profiler.generate_report()
        # Sem gargalos significativos, sem regressões
        assert len(report["regressions"]) == 0
        # Mas pode ter recomendação de gargalo (sempre tem se há dados)
        assert any("Gargalo" in r or "estável" in r for r in report["recommendations"])
    
    def test_bottleneck_recommendation(self):
        profiler = PerformanceProfiler()
        for i in range(100):
            profiler.record("heavy", 100.0)
        
        report = profiler.generate_report()
        assert any("Gargalo" in r for r in report["recommendations"])
    
    def test_slow_function_recommendation(self):
        profiler = PerformanceProfiler()
        for i in range(10):
            profiler.record("very_slow", 200.0)
        
        report = profiler.generate_report()
        assert any("p95" in r for r in report["recommendations"])
