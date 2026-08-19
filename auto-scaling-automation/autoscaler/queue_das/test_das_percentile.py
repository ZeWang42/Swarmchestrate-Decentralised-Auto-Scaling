import importlib
import sys
import types
import unittest
from pathlib import Path

module_dir = Path(__file__).resolve().parent
sys.path.insert(0, str(module_dir))

kubernetes_stub = types.ModuleType("kubernetes")
config_stub = types.ModuleType("kubernetes.config")
config_stub.load_incluster_config = lambda: None
config_stub.load_kube_config = lambda: None
kubernetes_stub.config = config_stub
sys.modules.setdefault("kubernetes", kubernetes_stub)
sys.modules.setdefault("kubernetes.config", config_stub)

monitoring_stub = types.ModuleType("monitoring")
class Monitor:  # pragma: no cover - simple stub
    pass
monitoring_stub.Monitor = Monitor
sys.modules.setdefault("monitoring", monitoring_stub)

execution_stub = types.ModuleType("execution")
class Executor:  # pragma: no cover - simple stub
    pass
execution_stub.Executor = Executor
sys.modules.setdefault("execution", execution_stub)

sys.modules.pop("DAS", None)
das_module = importlib.import_module("DAS")


class TestPercentileQueueing(unittest.TestCase):
    def test_normalize_latency_percentile_uses_p95_by_default(self) -> None:
        self.assertEqual(das_module.normalize_latency_percentile(None), ("P95", 0.95))

    def test_normalize_latency_percentile_supports_p90(self) -> None:
        self.assertEqual(das_module.normalize_latency_percentile("p90"), ("P90", 0.90))

    def test_waiting_percentile_mmc_increases_for_higher_tail_percentile(self) -> None:
        wq_p90 = das_module.waiting_percentile_mmc(1.0, 2.0, 1, 0.90)
        wq_p95 = das_module.waiting_percentile_mmc(1.0, 2.0, 1, 0.95)
        self.assertTrue(wq_p95 > 0.0)
        self.assertGreater(wq_p95, wq_p90)


if __name__ == "__main__":
    unittest.main()
