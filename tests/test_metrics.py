import unittest

from replayos.metrics import MetricsStore


class MetricsTests(unittest.TestCase):
    def test_alert_snapshot_and_prometheus(self) -> None:
        m = MetricsStore()
        m.observe_request("GET", "/x", 500, 12.0)
        m.observe_request("GET", "/x", 200, 8.0)
        m.observe_provider_error()

        snap = m.alert_snapshot(threshold=0.4, window_seconds=60, min_requests=1)
        self.assertTrue(snap.active)
        self.assertEqual(snap.total_requests, 2)

        text = m.render_prometheus(threshold=0.4, window_seconds=60, min_requests=1)
        self.assertIn("replayos_http_requests_total", text)
        self.assertIn("replayos_provider_errors_total", text)


if __name__ == "__main__":
    unittest.main()
