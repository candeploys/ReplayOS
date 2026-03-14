import unittest

from replayos.config import AuthConfig
from replayos.security import APIKeyAuth, SlidingWindowRateLimiter


class SecurityTests(unittest.TestCase):
    def test_api_key_auth(self) -> None:
        auth = APIKeyAuth(
            AuthConfig(
                require_api_key=True,
                allow_localhost_without_key=False,
                api_keys=("abc",),
            )
        )
        self.assertFalse(auth.validate(header_token="", client_ip="10.0.0.1").allowed)
        self.assertFalse(auth.validate(header_token="bad", client_ip="10.0.0.1").allowed)
        self.assertTrue(auth.validate(header_token="abc", client_ip="10.0.0.1").allowed)

    def test_rate_limiter(self) -> None:
        limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
        self.assertTrue(limiter.check("ip1").allowed)
        self.assertTrue(limiter.check("ip1").allowed)
        third = limiter.check("ip1")
        self.assertFalse(third.allowed)
        self.assertGreaterEqual(third.retry_after_seconds, 1)


if __name__ == "__main__":
    unittest.main()
