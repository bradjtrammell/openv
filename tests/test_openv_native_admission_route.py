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
        self.assertEqual(len(re.findall(r"netLibrary->SubmitCardResponse\s*\(", SOURCE)), 1)
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

    def test_native_start_failure_requests_real_teardown(self):
        start = SOURCE.index('const bool dispatched = openv::connection::DispatchNativeStart')
        failure = SOURCE.index('if (!dispatched)', start)
        end = SOURCE.index('return false;', failure)
        section = SOURCE[failure:end]
        self.assertIn('g_openvDisconnectRequested = true;', section)
        self.assertIn('dispatchLibrary->Disconnect();', section)
        self.assertIn('netLibrary == dispatchLibrary', section)
        self.assertIn('FinishOpenVConnectionIfIdle("native_start_failed")', section)

    def test_frame_reconciles_lost_native_idle_callback(self):
        frame = SOURCE.index('OnGameFrame.Connect([]()')
        end = SOURCE.index('Instance<ICoreGameInit>::Get()->OnGameRequestLoad', frame)
        section = SOURCE[frame:end]
        self.assertIn('ShouldFinalizeNativeClosure(', section)
        self.assertIn('g_connected, g_openvDisconnectRequested', section)
        self.assertIn('FinishOpenVConnectionIfIdle("native_idle_poll")', section)

    def test_async_disconnect_fences_native_admission(self):
        guard = "openv::connection::NativeAdmissionAllowed"
        card = SOURCE.index('OnConnectionCardPresent.Connect')
        arm = SOURCE.index('g_openvAdmissionCard.Arm(nonce, token)', card)
        self.assertIn(guard, SOURCE[card:arm])
        submit = SOURCE.index('L"openvSubmitJoinCode"')
        take = SOURCE.index('g_openvAdmissionCard.Take(nonce, code, cardToken)', submit)
        self.assertIn(guard, SOURCE[submit:take])
        cancel = SOURCE.index('L"openvCancelConnect"')
        disconnect = SOURCE.index('netLibrary->Disconnect();', cancel)
        self.assertIn('g_openvDisconnectRequested = true;', SOURCE[cancel:disconnect])
        self.assertIn('{ "cancelling", g_openvDisconnectRequested }', SOURCE)
        self.assertIn('g_openvDisconnectRequested = true;', SOURCE[
            SOURCE.index('static void FinishOpenVConnectionIfIdle'):
            SOURCE.index('static void UpdatePendingAuthPayload')])

    def test_all_native_terminal_paths_fence_reentrant_card_callbacks(self):
        for start, end in [
            ('static void DisconnectCmd()', 'OnKillNetwork("Disconnected.")'),
            ('g_openvAdmissionCard.Expired()', 'netLibrary->Disconnect();'),
            ('OnRequestBuildSwitch.Connect', 'InitializeBuildSwitch('),
            ('OnConnectionErrorRichEvent.Connect', 'std::string error = errorOrig;'),
            ('Legacy connection cards are unsupported', 'netLibrary->Disconnect();'),
            ('FinishOpenVConnectionIfIdle("admission_card_unavailable")',
             'FinishOpenVConnectionIfIdle("admission_card_unavailable")'),
            ('OnKillNetwork.Connect', 'FinishOpenVConnectionIfIdle("network_closed")'),
            ('resevman->TriggerEvent2("disconnecting"', 'OnKillNetwork("Disconnected.")'),
            ('L"cancelDefer"', 'netLibrary->Disconnect();'),
        ]:
            with self.subTest(path=start):
                begin = SOURCE.index(start)
                finish = SOURCE.index(end, begin)
                if start == 'FinishOpenVConnectionIfIdle("admission_card_unavailable")':
                    begin = SOURCE.rfind('g_openvAdmissionCard.DropPending()', 0, finish)
                self.assertIn('g_openvDisconnectRequested = true;', SOURCE[begin:finish])

    def test_legacy_card_is_rejected_not_submitted(self):
        self.assertIn('FinishOpenVConnectionIfIdle("legacy_card_unsupported")', SOURCE)
        self.assertIn('L"submitCardResponse"', SOURCE)
        self.assertIn("OpenV rejected unsupported legacy card response", SOURCE)


if __name__ == "__main__":
    unittest.main()
