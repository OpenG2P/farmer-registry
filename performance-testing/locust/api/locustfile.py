"""Minimal Locust entrypoint.

Use the per-use-case task files in the `staff-api/` and `partner-api/` folders as the
real load-test definitions. This root file is kept only as a compatibility
shim so `locust -f locustfile.py` still resolves without importing the full
blended workload.
"""

from locust import HttpUser


class RootUser(HttpUser):
    """Compatibility-only base user. Real workloads live in the subfolders."""

    abstract = True
    host = ""

