import unittest

from capcut_agent.silence_detect import compute_keep_segments


class TestComputeKeepSegments(unittest.TestCase):
    def test_basic_silence_in_middle(self):
        # 0-10s 영상, 4-6s가 무음
        segments = compute_keep_segments(10.0, [(4.0, 6.0)], padding=0.0, min_speech=0.0)
        self.assertEqual([(round(s.start, 3), round(s.end, 3)) for s in segments],
                          [(0.0, 4.0), (6.0, 10.0)])

    def test_no_silence_keeps_whole(self):
        segments = compute_keep_segments(10.0, [], padding=0.0, min_speech=0.0)
        self.assertEqual(len(segments), 1)
        self.assertAlmostEqual(segments[0].start, 0.0)
        self.assertAlmostEqual(segments[0].end, 10.0)

    def test_all_silence_falls_back_to_full(self):
        segments = compute_keep_segments(10.0, [(0.0, 10.0)], padding=0.0, min_speech=0.0)
        self.assertEqual(len(segments), 1)
        self.assertAlmostEqual(segments[0].duration, 10.0)

    def test_padding_prevents_word_clipping(self):
        segments = compute_keep_segments(10.0, [(4.0, 6.0)], padding=0.2, min_speech=0.0)
        self.assertEqual(len(segments), 2)
        self.assertAlmostEqual(segments[0].end, 4.2)
        self.assertAlmostEqual(segments[1].start, 5.8)

    def test_padding_merges_adjacent_segments(self):
        # 두 짧은 무음(4-4.3, 5-5.3)이 패딩(0.5s)으로 인해 겹치면 하나로 합쳐져야 함
        segments = compute_keep_segments(10.0, [(4.0, 4.3), (5.0, 5.3)], padding=0.5, min_speech=0.0)
        starts_ends = [(round(s.start, 3), round(s.end, 3)) for s in segments]
        self.assertEqual(starts_ends, [(0.0, 10.0)])

    def test_min_speech_drops_short_blips(self):
        # 4-4.05s (50ms) 발화는 노이즈로 간주해 제거
        segments = compute_keep_segments(10.0, [(0.0, 4.0), (4.05, 10.0)], padding=0.0, min_speech=0.15)
        starts_ends = [(round(s.start, 3), round(s.end, 3)) for s in segments]
        self.assertNotIn((4.0, 4.05), starts_ends)

    def test_overlapping_silences_merge(self):
        segments = compute_keep_segments(10.0, [(2.0, 5.0), (4.0, 7.0)], padding=0.0, min_speech=0.0)
        starts_ends = [(round(s.start, 3), round(s.end, 3)) for s in segments]
        self.assertEqual(starts_ends, [(0.0, 2.0), (7.0, 10.0)])


if __name__ == "__main__":
    unittest.main()
