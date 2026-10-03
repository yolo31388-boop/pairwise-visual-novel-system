import unittest

import pytest

from visual_novel.system import (
    Choice,
    ChoiceError,
    SaveSlotError,
    VisualNovelSystem,
)


def build_game():
    """A small branching visual novel used across the tests."""
    game = VisualNovelSystem()
    game.register_attribute("affection", initial=0, min_value=0, max_value=100)
    game.add_scene("start", text="You meet her at the station.", choices=[
        Choice(id="greet", text="Say hello", effects={"affection": 10},
               target="date", unique=True),
        Choice(id="ignore", text="Walk past", effects={"affection": -0},
               target="alone"),
        Choice(id="confess", text="Confess your love",
               conditions={"affection": 50}, target="romance", unique=True),
    ])
    game.add_scene("date", text="You share a coffee.", choices=[
        Choice(id="gift", text="Give a gift", effects={"affection": 50},
               target="finale", unique=True),
    ])
    game.add_scene("alone", text="The train leaves without you.")
    game.add_scene("romance", text="She smiles.", condition={"affection": 50})
    game.add_scene("finale", text="The festival begins.")
    return game


class TestVisualNovelSystem(unittest.TestCase):

    # ---- choices ------------------------------------------------------
    def test_make_choice(self):
        """选项做分支记录：选了什么会影响后续"""
        game = build_game()
        result = game.make_choice("greet")
        self.assertIsNotNone(result)
        self.assertIn("greet", game.get_choice_history())
        self.assertEqual(game.current_scene, "date")

    def test_choice_branch_recorded(self):
        """不同的选择记录不同的分支历史"""
        game_a = build_game()
        game_a.make_choice("greet")
        game_b = build_game()
        game_b.make_choice("ignore")
        self.assertEqual(game_a.get_choice_history(), ["greet"])
        self.assertEqual(game_b.get_choice_history(), ["ignore"])
        self.assertNotEqual(game_a.current_scene, game_b.current_scene)

    def test_conditional_choice(self):
        """条件选项：属性不够不能选"""
        game = build_game()
        with pytest.raises(ChoiceError):
            game.make_choice("confess")
        self.assertNotIn("confess", [c.id for c in game.available_choices()])
        game.update_attribute("affection", 60)
        self.assertIn("confess", [c.id for c in game.available_choices()])
        game.make_choice("confess")
        self.assertEqual(game.current_scene, "romance")

    def test_unique_choice(self):
        """唯一选项：重要选项不能反复选"""
        game = build_game()
        game.make_choice("greet")
        with pytest.raises(ChoiceError):
            game.make_choice("greet")
        self.assertEqual(game.get_choice_history().count("greet"), 1)

    # ---- attributes ---------------------------------------------------
    def test_update_attribute(self):
        """属性做影响：好感度高低剧情不一样"""
        game = VisualNovelSystem()
        result = game.update_attribute("affection", 10)
        self.assertIsNotNone(result)
        self.assertEqual(game.get_attribute("affection"), 10)
        low = build_game()
        high = build_game()
        high.update_attribute("affection", 60)
        self.assertNotEqual([c.id for c in low.available_choices()],
                            [c.id for c in high.available_choices()])

    def test_attribute_bounds(self):
        """属性做上限下限：不能无限加"""
        game = build_game()
        game.update_attribute("affection", 999)
        self.assertEqual(game.get_attribute("affection"), 100)
        game.update_attribute("affection", -999)
        self.assertEqual(game.get_attribute("affection"), 0)

    def test_attribute_display(self):
        """属性做显示：玩家能看到当前属性"""
        game = build_game()
        game.update_attribute("affection", 30)
        display = game.display_attributes()
        self.assertIn("affection", display)
        self.assertIn("30", display)

    # ---- story --------------------------------------------------------
    def test_advance_story(self):
        """剧情做分支：推进返回剧情节点，没有后继时返回 None"""
        game = build_game()
        scene = game.advance_story("date")
        self.assertIsNotNone(scene)
        self.assertEqual(scene.id, "date")
        game.advance_story("alone")
        self.assertIsNone(game.advance_story())

    def test_story_branching(self):
        """选了 A 走 A 线，选了 B 走 B 线"""
        game = build_game()
        game.make_choice("greet")
        self.assertEqual(game.get_current_scene().text, "You share a coffee.")
        game2 = build_game()
        game2.make_choice("ignore")
        self.assertEqual(game2.get_current_scene().text,
                         "The train leaves without you.")

    def test_story_jump(self):
        """剧情做跳转：选了选项跳到对应剧情"""
        game = build_game()
        game.make_choice("greet")
        game.make_choice("gift")
        self.assertEqual(game.current_scene, "finale")

    def test_story_condition(self):
        """剧情做条件：需要属性的剧情不能无条件看"""
        game = build_game()
        with pytest.raises(ChoiceError):
            game.advance_story("romance")
        game.update_attribute("affection", 50)
        scene = game.advance_story("romance")
        self.assertEqual(scene.id, "romance")

    # ---- saves --------------------------------------------------------
    def test_save_game(self):
        """存档存选项历史：读档后知道选过什么"""
        game = build_game()
        result = game.save_game()
        self.assertIsNotNone(result)
        game.make_choice("greet")
        game.save_game(slot=1)
        game.load_game(slot=0)
        self.assertEqual(game.get_choice_history(), [])
        game.load_game(slot=1)
        self.assertEqual(game.get_choice_history(), ["greet"])

    def test_save_story_position(self):
        """存档存剧情位置：读档不从头开始"""
        game = build_game()
        game.make_choice("greet")
        game.save_game(slot=1)
        game.make_choice("gift")
        self.assertEqual(game.current_scene, "finale")
        game.load_game(slot=1)
        self.assertEqual(game.current_scene, "date")

    def test_save_slots(self):
        """存档做槽位：不止一个存档"""
        game = build_game()
        game.make_choice("greet")
        game.save_game(slot=0)
        game.make_choice("gift")
        game.save_game(slot=1)
        self.assertEqual(game.list_saves(), [0, 1])
        game.load_game(slot=0)
        self.assertEqual(game.current_scene, "date")
        game.load_game(slot=1)
        self.assertEqual(game.current_scene, "finale")
        with pytest.raises(SaveSlotError):
            game.load_game(slot=2)

    # ---- endings ------------------------------------------------------
    def test_calculate_ending(self):
        """结局做属性判定：属性不同结局不同"""
        game = VisualNovelSystem()
        self.assertIsNotNone(game.calculate_ending())
        low = build_game()
        high = build_game()
        high.update_attribute("affection", 80)
        self.assertEqual(low.calculate_ending().id, "bad")
        self.assertEqual(high.calculate_ending().id, "good")

    def test_hidden_ending(self):
        """结局做隐藏结局：不止好结局坏结局"""
        game = build_game()
        game.register_ending("true", title="True Ending", hidden=True,
                             priority=100, conditions={"affection": 100},
                             required_choices=["gift"])
        self.assertNotIn("true", game.available_endings())
        self.assertIn("true", game.available_endings(include_hidden=True))
        game.make_choice("greet")
        game.make_choice("gift")
        game.update_attribute("affection", 100)
        ending = game.calculate_ending()
        self.assertEqual(ending.id, "true")
        self.assertTrue(ending.hidden)

    def test_ending_review(self):
        """结局做回顾：知道为什么是这个结局"""
        game = build_game()
        game.make_choice("greet")
        game.update_attribute("affection", 80)
        ending = game.calculate_ending()
        self.assertIn("affection", ending.review)
        self.assertIn("greet", ending.review)
        self.assertIn("Good Ending", ending.review)


if __name__ == "__main__":
    unittest.main()
