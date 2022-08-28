from base.client_base import TestcaseBase
from utils.util_log import test_log as log


class TestDeployBase(TestcaseBase):

    def teardown_method(self, method):
        log.info(("*" * 35) + " teardown " + ("*" * 35))
        log.info(f"[teardown_method] Start teardown test case {method.__name__}...")
        log.info("skip drop collection")
