"""
pairwise-visual-novel-system - VisualNovelSystem

This module contains a deliberately broken implementation.
Fix all bugs so that tests pass.
"""


class VisualNovelSystem:
    def __init__(self):
        self.state = {}

    def make_choice(self, *args, **kwargs):
        """BUG: 选项不做分支记录，选了什么不影响后续"""
        return None

    def update_attribute(self, *args, **kwargs):
        """BUG: 属性不做影响，好感度高低剧情一样"""
        return None

    def advance_story(self, *args, **kwargs):
        """BUG: 剧情不做分支，所有选项走同一条线"""
        return None

    def save_game(self, *args, **kwargs):
        """BUG: 存档不存选项历史，读档后不知道选过什么"""
        return None

    def calculate_ending(self, *args, **kwargs):
        """BUG: 结局不做属性判定，任何属性都是同一个结局"""
        return None

