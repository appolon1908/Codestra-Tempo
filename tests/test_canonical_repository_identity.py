from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from scripts import validate_codestra_enterprise_profile as policy


class CanonicalRepositoryIdentityTests(unittest.TestCase):
    def test_canonical_same_repository_profile_is_accepted(self):
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "appolon1908/Codestra-Tempo"}):
            self.assertEqual(policy.validate_profile()["status"], "CONFIG_PREPARED_NOT_DEPLOYED")

    def test_former_and_unrelated_repository_names_are_rejected(self):
        for repository in ("ingtrader21-spec/Codestra-Tempo", "appolon1908-hue/Codestra-Tempo", "other/Codestra-Tempo", "appolon1908/other"):
            with self.subTest(repository=repository), patch.dict(os.environ, {"GITHUB_REPOSITORY": repository}):
                with self.assertRaises(SystemExit):
                    policy.validate_profile()
