"""
Testes para Dependency Graph v3.6
"""

import unittest
import time
from dependency_graph import DependencyGraph, ImpactReport


class TestDependencyNode(unittest.TestCase):
    """Testes para criação e manipulação de nós."""

    def setUp(self):
        self.graph = DependencyGraph()

    def test_add_node(self):
        """Testa adição de nó."""
        self.graph.add_node("api1", "https://api1.com/health")
        self.assertIn("api1", self.graph.nodes)
        self.assertEqual(self.graph.nodes["api1"].url, "https://api1.com/health")
        self.assertEqual(self.graph.nodes["api1"].status, "unknown")

    def test_add_node_with_metadata(self):
        """Testa adição de nó com metadata."""
        self.graph.add_node("api1", "https://api1.com", {"team": "backend"})
        self.assertEqual(self.graph.nodes["api1"].metadata["team"], "backend")

    def test_add_duplicate_node(self):
        """Testa adição de nó duplicado (não deve duplicar)."""
        self.graph.add_node("api1", "https://api1.com")
        self.graph.add_node("api1", "https://api1.com/v2")  # mesmo nome
        self.assertEqual(len(self.graph.nodes), 1)
        self.assertEqual(self.graph.nodes["api1"].url, "https://api1.com")

    def test_remove_node(self):
        """Testa remoção de nó."""
        self.graph.add_node("api1", "https://api1.com")
        result = self.graph.remove_node("api1")
        self.assertTrue(result)
        self.assertNotIn("api1", self.graph.nodes)

    def test_remove_nonexistent_node(self):
        """Testa remoção de nó inexistente."""
        result = self.graph.remove_node("nonexistent")
        self.assertFalse(result)


class TestDependencies(unittest.TestCase):
    """Testes para relações de dependência."""

    def setUp(self):
        self.graph = DependencyGraph()
        self.graph.add_node("frontend", "https://frontend.com")
        self.graph.add_node("api", "https://api.com")
        self.graph.add_node("db", "https://db.com")

    def test_add_dependency(self):
        """Testa adição de dependência."""
        result = self.graph.add_dependency("frontend", "api")
        self.assertTrue(result)
        self.assertIn("api", self.graph.nodes["frontend"].dependencies)
        self.assertIn("frontend", self.graph.nodes["api"].dependents)

    def test_add_dependency_nonexistent(self):
        """Testa adição de dependência com nó inexistente."""
        result = self.graph.add_dependency("frontend", "nonexistent")
        self.assertFalse(result)

    def test_remove_dependency(self):
        """Testa remoção de dependência."""
        self.graph.add_dependency("frontend", "api")
        result = self.graph.remove_dependency("frontend", "api")
        self.assertTrue(result)
        self.assertNotIn("api", self.graph.nodes["frontend"].dependencies)
        self.assertNotIn("frontend", self.graph.nodes["api"].dependents)

    def test_remove_node_cascades(self):
        """Testa que remover nó remove suas conexões."""
        self.graph.add_dependency("frontend", "api")
        self.graph.add_dependency("api", "db")
        self.graph.remove_node("api")

        self.assertNotIn("api", self.graph.nodes["frontend"].dependencies)
        self.assertNotIn("api", self.graph.nodes["db"].dependents)


class TestDependencyQueries(unittest.TestCase):
    """Testes para consultas de dependência."""

    def setUp(self):
        self.graph = DependencyGraph()
        # Cadeia: frontend -> api -> db
        #         frontend -> cache -> db
        #         admin -> api
        for name in ["frontend", "api", "db", "cache", "admin"]:
            self.graph.add_node(name, f"https://{name}.com")

        self.graph.add_dependency("frontend", "api")
        self.graph.add_dependency("frontend", "cache")
        self.graph.add_dependency("api", "db")
        self.graph.add_dependency("cache", "db")
        self.graph.add_dependency("admin", "api")

    def test_get_dependencies_direct(self):
        """Testa dependências diretas."""
        deps = self.graph.get_dependencies("frontend", recursive=False)
        self.assertEqual(deps, {"api", "cache"})

    def test_get_dependencies_recursive(self):
        """Testa dependências transitivas."""
        deps = self.graph.get_dependencies("frontend", recursive=True)
        self.assertEqual(deps, {"api", "cache", "db"})

    def test_get_dependents_direct(self):
        """Testa dependentes diretos."""
        deps = self.graph.get_dependents("api", recursive=False)
        self.assertEqual(deps, {"frontend", "admin"})

    def test_get_dependents_recursive(self):
        """Testa dependentes transitivos."""
        deps = self.graph.get_dependents("db", recursive=True)
        self.assertEqual(deps, {"api", "cache", "frontend", "admin"})

    def test_get_dependencies_nonexistent(self):
        """Testa dependências de nó inexistente."""
        deps = self.graph.get_dependencies("nonexistent")
        self.assertEqual(deps, set())


class TestImpactAnalysis(unittest.TestCase):
    """Testes para análise de impacto."""

    def setUp(self):
        self.graph = DependencyGraph()
        # db é crítico: api1, api2, cache dependem dele
        for name in ["frontend", "api1", "api2", "cache", "db"]:
            self.graph.add_node(name, f"https://{name}.com")

        self.graph.add_dependency("frontend", "api1")
        self.graph.add_dependency("frontend", "api2")
        self.graph.add_dependency("api1", "db")
        self.graph.add_dependency("api2", "db")
        self.graph.add_dependency("cache", "db")

    def test_calculate_impact_critical(self):
        """Testa impacto de endpoint crítico (db)."""
        report = self.graph.calculate_impact("db")
        self.assertIsNotNone(report)
        self.assertEqual(report.failed_endpoint, "db")
        self.assertIn("api1", report.direct_impact)
        self.assertIn("api2", report.direct_impact)
        self.assertIn("cache", report.direct_impact)
        self.assertIn("frontend", report.transitive_impact)
        self.assertEqual(report.total_affected, 4)
        self.assertEqual(report.severity, "high")

    def test_calculate_impact_low(self):
        """Testa impacto de endpoint com poucos dependentes."""
        report = self.graph.calculate_impact("frontend")
        self.assertEqual(report.total_affected, 0)
        self.assertEqual(report.severity, "low")

    def test_calculate_impact_nonexistent(self):
        """Testa impacto de endpoint inexistente."""
        report = self.graph.calculate_impact("nonexistent")
        self.assertIsNone(report)

    def test_impact_history(self):
        """Testa histórico de impactos."""
        self.graph.calculate_impact("db")
        self.graph.calculate_impact("api1")
        self.assertEqual(len(self.graph.impact_history), 2)


class TestCycleDetection(unittest.TestCase):
    """Testes para detecção de ciclos."""

    def setUp(self):
        self.graph = DependencyGraph()

    def test_no_cycles(self):
        """Testa grafo sem ciclos."""
        for name in ["a", "b", "c"]:
            self.graph.add_node(name, f"https://{name}.com")
        self.graph.add_dependency("a", "b")
        self.graph.add_dependency("b", "c")

        cycles = self.graph.find_cycles()
        self.assertEqual(len(cycles), 0)

    def test_simple_cycle(self):
        """Testa ciclo simples: a -> b -> a."""
        for name in ["a", "b"]:
            self.graph.add_node(name, f"https://{name}.com")
        self.graph.add_dependency("a", "b")
        self.graph.add_dependency("b", "a")

        cycles = self.graph.find_cycles()
        self.assertEqual(len(cycles), 1)

    def test_complex_cycle(self):
        """Testa ciclo complexo: a -> b -> c -> a."""
        for name in ["a", "b", "c"]:
            self.graph.add_node(name, f"https://{name}.com")
        self.graph.add_dependency("a", "b")
        self.graph.add_dependency("b", "c")
        self.graph.add_dependency("c", "a")

        cycles = self.graph.find_cycles()
        self.assertEqual(len(cycles), 1)


class TestCriticalPaths(unittest.TestCase):
    """Testes para caminhos críticos."""

    def setUp(self):
        self.graph = DependencyGraph()
        # db tem mais dependentes
        for name in ["frontend", "api", "cache", "db", "standalone"]:
            self.graph.add_node(name, f"https://{name}.com")

        self.graph.add_dependency("frontend", "api")
        self.graph.add_dependency("frontend", "cache")
        self.graph.add_dependency("api", "db")
        self.graph.add_dependency("cache", "db")

    def test_critical_paths_order(self):
        """Testa ordenação por criticidade."""
        paths = self.graph.get_critical_paths()
        # db deve ser primeiro (mais dependentes)
        self.assertEqual(paths[0][0], "db")
        self.assertGreater(paths[0][1], paths[-1][1])

    def test_standalone_has_zero_criticality(self):
        """Testa endpoint sem dependentes."""
        paths = self.graph.get_critical_paths()
        standalone = [p for p in paths if p[0] == "standalone"]
        self.assertEqual(len(standalone), 1)
        self.assertEqual(standalone[0][1], 0)


class TestStatusUpdates(unittest.TestCase):
    """Testes para atualização de status."""

    def setUp(self):
        self.graph = DependencyGraph()
        self.graph.add_node("api", "https://api.com")

    def test_update_status(self):
        """Testa atualização de status."""
        self.graph.update_status("api", "up", 0.15)
        node = self.graph.nodes["api"]
        self.assertEqual(node.status, "up")
        self.assertEqual(node.response_time, 0.15)
        self.assertIsNotNone(node.last_check)

    def test_update_status_nonexistent(self):
        """Testa atualização de status de nó inexistente."""
        # Não deve levantar exceção
        self.graph.update_status("nonexistent", "up")


class TestSerialization(unittest.TestCase):
    """Testes para serialização."""

    def setUp(self):
        self.graph = DependencyGraph()
        self.graph.add_node("api", "https://api.com")
        self.graph.add_node("db", "https://db.com")
        self.graph.add_dependency("api", "db")
        self.graph.update_status("api", "up", 0.1)

    def test_to_dict(self):
        """Testa serialização para dict."""
        data = self.graph.to_dict()
        self.assertIn("nodes", data)
        self.assertIn("stats", data)
        self.assertIn("api", data["nodes"])
        self.assertIn("db", data["nodes"]["api"]["dependencies"])

    def test_get_topology(self):
        """Testa topologia para visualização."""
        topo = self.graph.get_topology()
        self.assertEqual(len(topo["nodes"]), 2)
        self.assertEqual(len(topo["edges"]), 1)
        self.assertEqual(topo["edges"][0]["source"], "api")
        self.assertEqual(topo["edges"][0]["target"], "db")

    def test_get_stats(self):
        """Testa estatísticas."""
        stats = self.graph.get_stats()
        self.assertEqual(stats["total_nodes"], 2)
        self.assertEqual(stats["total_edges"], 1)


class TestThreadSafety(unittest.TestCase):
    """Testes para thread safety."""

    def test_concurrent_operations(self):
        """Testa operações concorrentes."""
        graph = DependencyGraph()

        def add_nodes():
            for i in range(100):
                graph.add_node(f"node_{i}", f"https://node{i}.com")

        def add_dependencies():
            for i in range(99):
                graph.add_dependency(f"node_{i}", f"node_{i+1}")

        import threading
        t1 = threading.Thread(target=add_nodes)
        t2 = threading.Thread(target=add_dependencies)

        t1.start()
        t2.start()
        t1.join()
        t2.join()

        # Não deve ter crashado
        self.assertLessEqual(len(graph.nodes), 100)


if __name__ == "__main__":
    unittest.main()
