import unittest
from unittest.mock import Mock, patch

from ins import swipe_feed


class InstagramSwipeTests(unittest.TestCase):
    def setUp(self):
        self.device = Mock()
        self.target = self.device.return_value
        self.target.count = 1
        self.target.info = {"visibleBounds": {"left": 100, "top": 200, "right": 900, "bottom": 1200}}
        self.cfg = {"selectors": {"feed": {"resourceId": "android:id/list", "scrollable": True}},
                    "gestures": {"scroll_steps": 40, "settle_seconds": 0.1}}
        self.before, self.after = Mock(), Mock()
        self.before.fingerprint.return_value = ('first post',)
        self.after.fingerprint.return_value = ('second post',)
        self.feed = object()

    def swipe(self, direction):
        with patch('ins.capture', side_effect=[self.before, self.after]), \
                patch('ins.instagram_feed', return_value=self.feed), patch('ins.time.sleep'):
            return swipe_feed(self.device, 'com.instagram.android', self.cfg, direction)

    def test_down_and_up_stay_inside_visible_list_and_reverse_direction(self):
        for direction, start, end in [('browse_down',1050,350), ('browse_up',350,1050)]:
            self.device.reset_mock()
            result = self.swipe(direction)
            self.device.swipe.assert_called_once_with(500,start,500,end,steps=40)
            self.assertTrue(result['content_layout_changed'])
            self.assertFalse(result['scroll_verified'])
            self.target.scroll.vert.forward.assert_not_called()
            self.target.scroll.vert.backward.assert_not_called()

    def test_ambiguous_list_never_swipes(self):
        self.target.count = 2
        with self.assertRaisesRegex(RuntimeError,'exactly one'):
            self.swipe('browse_down')
        self.device.swipe.assert_not_called()

    def test_leaving_feed_is_reported_as_failure(self):
        with patch('ins.capture',side_effect=[self.before,self.after]), \
                patch('ins.instagram_feed',side_effect=[self.feed,None]), patch('ins.time.sleep'):
            with self.assertRaisesRegex(RuntimeError,'left the Instagram home feed'):
                swipe_feed(self.device,'com.instagram.android',self.cfg,'browse_down')

    def test_unchanged_layout_does_not_claim_verified_movement(self):
        self.after.fingerprint.return_value = self.before.fingerprint.return_value
        result = self.swipe('browse_up')
        self.assertFalse(result['content_layout_changed'])
        self.assertFalse(result['scroll_verified'])


if __name__ == '__main__':
    unittest.main()
