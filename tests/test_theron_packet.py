import unittest

from scripts import build_theron_packet


class TheronPacketTests(unittest.TestCase):
    def test_build_packet_for_personification_task(self):
        packet = build_theron_packet.build_packet("c08")

        self.assertEqual(packet["task_id"], "c08")
        self.assertEqual(packet["lane"], "creative")
        self.assertEqual(packet["family"], "personification")
        self.assertEqual(packet["condition"], "critique_off")
        self.assertIn("THERON LAB REQUEST", packet["message_to_send"])
        self.assertIn("Return only the final artifact text.", packet["message_to_send"])
        self.assertEqual(packet["submission_template"]["generator_provider"], "theron_manual")
        self.assertEqual(packet["submission_template"]["generator_role_id"], "theron")

    def test_unknown_task_raises(self):
        with self.assertRaises(KeyError):
            build_theron_packet.build_packet("nope")


if __name__ == "__main__":
    unittest.main()
