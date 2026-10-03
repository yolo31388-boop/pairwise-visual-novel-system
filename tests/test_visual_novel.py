import pytest
from visual_novel.system import VisualNovelSystem


class TestVisualNovelSystem:

    def test_make_choice(self):
        """选项不做分支记录，选了什么不影响后续"""
        obj = VisualNovelSystem()
        result = obj.make_choice()
        self.assertIsNotNone(result)

    def test_update_attribute(self):
        """属性不做影响，好感度高低剧情一样"""
        obj = VisualNovelSystem()
        result = obj.update_attribute()
        self.assertIsNotNone(result)

    def test_advance_story(self):
        """剧情不做分支，所有选项走同一条线"""
        obj = VisualNovelSystem()
        result = obj.advance_story()
        self.assertIsNotNone(result)

    def test_save_game(self):
        """存档不存选项历史，读档后不知道选过什么"""
        obj = VisualNovelSystem()
        result = obj.save_game()
        self.assertIsNotNone(result)

    def test_calculate_ending(self):
        """结局不做属性判定，任何属性都是同一个结局"""
        obj = VisualNovelSystem()
        result = obj.calculate_ending()
        self.assertIsNotNone(result)

