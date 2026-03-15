"""
Mengão Monitor v3.6 - Dependency Graph
Mapeia dependências entre endpoints e calcula impacto de falhas.
"""

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class DependencyNode:
    """Nó no grafo de dependências."""
    name: str
    url: str
    status: str = "unknown"  # unknown, up, down, degraded
    response_time: Optional[float] = None
    last_check: Optional[float] = None
    dependents: Set[str] = field(default_factory=set)  # quem depende de mim
    dependencies: Set[str] = field(default_factory=set)  # de quem eu dependo
    metadata: Dict = field(default_factory=dict)


@dataclass
class ImpactReport:
    """Relatório de impacto de uma falha."""
    failed_endpoint: str
    direct_impact: List[str]  # endpoints afetados diretamente
    transitive_impact: List[str]  # endpoints afetados indiretamente
    total_affected: int
    severity: str  # low, medium, high, critical
    timestamp: float = field(default_factory=time.time)


class DependencyGraph:
    """Grafo de dependências entre endpoints monitorados."""

    def __init__(self):
        self.nodes: Dict[str, DependencyNode] = {}
        self.lock = threading.RLock()
        self.impact_history: List[ImpactReport] = []
        self.max_history = 100

    def add_node(self, name: str, url: str, metadata: Optional[Dict] = None) -> None:
        """Adiciona um nó ao grafo."""
        with self.lock:
            if name not in self.nodes:
                self.nodes[name] = DependencyNode(
                    name=name,
                    url=url,
                    metadata=metadata or {}
                )

    def remove_node(self, name: str) -> bool:
        """Remove um nó e todas suas conexões."""
        with self.lock:
            if name not in self.nodes:
                return False

            node = self.nodes[name]

            # Remove das dependências de outros nós
            for dep_name in node.dependencies:
                if dep_name in self.nodes:
                    self.nodes[dep_name].dependents.discard(name)

            for dep_name in node.dependents:
                if dep_name in self.nodes:
                    self.nodes[dep_name].dependencies.discard(name)

            del self.nodes[name]
            return True

    def add_dependency(self, dependent: str, dependency: str) -> bool:
        """Adiciona relação: dependent depende de dependency."""
        with self.lock:
            if dependent not in self.nodes or dependency not in self.nodes:
                return False

            self.nodes[dependent].dependencies.add(dependency)
            self.nodes[dependency].dependents.add(dependent)
            return True

    def remove_dependency(self, dependent: str, dependency: str) -> bool:
        """Remove relação de dependência."""
        with self.lock:
            if dependent not in self.nodes or dependency not in self.nodes:
                return False

            self.nodes[dependent].dependencies.discard(dependency)
            self.nodes[dependency].dependents.discard(dependent)
            return True

    def update_status(self, name: str, status: str,
                      response_time: Optional[float] = None) -> None:
        """Atualiza status de um endpoint."""
        with self.lock:
            if name in self.nodes:
                node = self.nodes[name]
                node.status = status
                node.response_time = response_time
                node.last_check = time.time()

    def get_dependencies(self, name: str, recursive: bool = False) -> Set[str]:
        """Retorna dependências de um endpoint."""
        with self.lock:
            if name not in self.nodes:
                return set()

            if not recursive:
                return self.nodes[name].dependencies.copy()

            # BFS para dependências transitivas
            visited = set()
            queue = deque([name])
            result = set()

            while queue:
                current = queue.popleft()
                if current in visited:
                    continue
                visited.add(current)

                if current != name:
                    result.add(current)

                if current in self.nodes:
                    for dep in self.nodes[current].dependencies:
                        if dep not in visited:
                            queue.append(dep)

            return result

    def get_dependents(self, name: str, recursive: bool = False) -> Set[str]:
        """Retorna quem depende de um endpoint."""
        with self.lock:
            if name not in self.nodes:
                return set()

            if not recursive:
                return self.nodes[name].dependents.copy()

            # BFS para dependentes transitivos
            visited = set()
            queue = deque([name])
            result = set()

            while queue:
                current = queue.popleft()
                if current in visited:
                    continue
                visited.add(current)

                if current != name:
                    result.add(current)

                if current in self.nodes:
                    for dep in self.nodes[current].dependents:
                        if dep not in visited:
                            queue.append(dep)

            return result

    def calculate_impact(self, name: str) -> Optional[ImpactReport]:
        """Calcula impacto de falha de um endpoint."""
        with self.lock:
            if name not in self.nodes:
                return None

            direct = list(self.nodes[name].dependents)
            transitive_set = self.get_dependents(name, recursive=True)
            transitive = list(transitive_set - set(direct))

            total = len(direct) + len(transitive)

            # Severidade baseada no impacto
            if total == 0:
                severity = "low"
            elif total <= 2:
                severity = "medium"
            elif total <= 5:
                severity = "high"
            else:
                severity = "critical"

            report = ImpactReport(
                failed_endpoint=name,
                direct_impact=direct,
                transitive_impact=transitive,
                total_affected=total,
                severity=severity
            )

            self.impact_history.append(report)
            if len(self.impact_history) > self.max_history:
                self.impact_history = self.impact_history[-self.max_history:]

            return report

    def find_cycles(self) -> List[List[str]]:
        """Detecta ciclos no grafo (dependências circulares)."""
        with self.lock:
            cycles = []
            visited = set()
            rec_stack = set()

            def dfs(node: str, path: List[str]) -> None:
                visited.add(node)
                rec_stack.add(node)
                path.append(node)

                if node in self.nodes:
                    for dep in self.nodes[node].dependencies:
                        if dep not in visited:
                            dfs(dep, path.copy())
                        elif dep in rec_stack:
                            # Encontrou ciclo
                            cycle_start = path.index(dep)
                            cycles.append(path[cycle_start:] + [dep])

                rec_stack.discard(node)

            for node_name in self.nodes:
                if node_name not in visited:
                    dfs(node_name, [])

            return cycles

    def get_critical_paths(self) -> List[Tuple[str, int]]:
        """Retorna endpoints ordenados por criticidade (mais dependentes primeiro)."""
        with self.lock:
            criticality = []
            for name, node in self.nodes.items():
                # Criticidade = dependentes diretos + dependentes transitivos
                total_dependents = len(self.get_dependents(name, recursive=True))
                criticality.append((name, total_dependents))

            criticality.sort(key=lambda x: x[1], reverse=True)
            return criticality

    def get_stats(self) -> Dict:
        """Estatísticas do grafo."""
        with self.lock:
            total_nodes = len(self.nodes)
            total_edges = sum(len(n.dependencies) for n in self.nodes.values())
            statuses = defaultdict(int)
            for node in self.nodes.values():
                statuses[node.status] += 1

            return {
                "total_nodes": total_nodes,
                "total_edges": total_edges,
                "statuses": dict(statuses),
                "impact_reports": len(self.impact_history),
                "cycles": len(self.find_cycles())
            }

    def to_dict(self) -> Dict:
        """Serializa grafo para dict."""
        with self.lock:
            return {
                "nodes": {
                    name: {
                        "url": node.url,
                        "status": node.status,
                        "response_time": node.response_time,
                        "last_check": node.last_check,
                        "dependents": list(node.dependents),
                        "dependencies": list(node.dependencies),
                        "metadata": node.metadata
                    }
                    for name, node in self.nodes.items()
                },
                "stats": self.get_stats()
            }

    def get_topology(self) -> Dict:
        """Retorna topologia do grafo para visualização."""
        with self.lock:
            nodes = []
            edges = []

            for name, node in self.nodes.items():
                nodes.append({
                    "id": name,
                    "url": node.url,
                    "status": node.status,
                    "response_time": node.response_time
                })

                for dep in node.dependencies:
                    edges.append({
                        "source": name,
                        "target": dep,
                        "type": "depends_on"
                    })

            return {"nodes": nodes, "edges": edges}
