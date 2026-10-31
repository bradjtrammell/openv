"""Source-level regression for native OpenV admission routing.

The portable C++ contract is compiled and executed separately. This test
checks that its production NetLibrary integration remains wired fail-closed.
"""
from pathlib import Path
import re
import unittest

SOURCE = (Path(__file__).resolve().parents[1] /
          "code/components/glue/src/ConnectToNative.cpp").read_text(encoding="utf-8")


class NativeAdmissionRouteTests(unittest.TestCase):
    def test_only_join_code_submits_to_netlibrary(self):
        self.assertEqual(len(re.findall(r"netLibrary->SubmitCardResponse\\s*\\(", SOURCE)), 1)
        self.assertIn("g_openvAdmissionCard.Take(nonce, code, cardToken)", SOURCE)
        self.assertIn('nlohmann::json::object({ { "join_code", code } })', SOURCE)
        self.assertNotIn("g_cardConnectionToken", SOURCE)
        self.assertNotIn("XBR_InterceptCardResponse", SOURCE)

    def test_native_frame_watchdog_and_idle_cleanup(self):
        self.assertIn("g_openvAdmissionCard.Expired()", SOURCE)
        self.assertIn('FinishOpenVConnectionIfIdle("admission_timeout")', SOURCE)
        self.assertIn("currentState == NetLibrary::CS_IDLE", SOURCE)
        self.assertIn('FinishOpenVConnectionIfIdle("native_idle")', SOURCE)
        self.assertIn("g_openvAdmissionCard.DropPending()", SOURCE)

    def test_legacy_card_is_rejected_not_submitted(self):
        self.assertIn('FinishOpenVConnectionIfIdle("legacy_card_unsupported")', SOURCE)
        self.assertIn('L"submitCardResponse"', SOURCE)
        self.assertIn("OpenV rejected unsupported legacy card response", SOURCE)


if __name__ == "__main__":
    unittest.main()
