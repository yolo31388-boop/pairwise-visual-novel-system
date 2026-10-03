"""
pairwise-visual-novel-system - VisualNovelSystem

A visual novel engine core with:

- Choices that are recorded, gated by attribute conditions, and unique
  (important choices cannot be repeated).
- Attributes with min/max bounds that affect the story and are displayable.
- A branching story graph with jumps and per-scene conditions.
- Save slots that persist choice history and the current story position.
- Endings decided by attributes, including hidden endings, with a review
  of why an ending was reached.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


class ChoiceError(Exception):
    """Raised when a choice cannot be made (unknown, locked, or repeated)."""


class SaveSlotError(Exception):
    """Raised when a save slot is invalid or empty."""


@dataclass
class Choice:
    """A single choice the player can make."""

    id: str
    text: str = ""
    # Attribute requirements: {"affection": 10} or {"affection": {"min": 10, "max": 50}}
    conditions: Dict[str, Any] = field(default_factory=dict)
    # Attribute effects applied when the choice is made: {"affection": +5}
    effects: Dict[str, float] = field(default_factory=dict)
    # Scene to jump to after this choice; None follows the scene's default next.
    target: Optional[str] = None
    # Unique choices can only be picked once per playthrough.
    unique: bool = False
    # Scene this choice belongs to (filled in when registered with a scene).
    scene: Optional[str] = None

    def is_available(self, attributes: Dict[str, float]) -> bool:
        """A choice is only selectable when all attribute conditions hold."""
        for name, requirement in self.conditions.items():
            value = attributes.get(name, 0)
            if isinstance(requirement, dict):
                if "min" in requirement and value < requirement["min"]:
                    return False
                if "max" in requirement and value > requirement["max"]:
                    return False
            elif value < requirement:
                return False
        return True


@dataclass
class Scene:
    """A story node with text, choices, and an optional entry condition."""

    id: str
    text: str = ""
    choices: List[Choice] = field(default_factory=list)
    # Default next scene when a choice has no explicit target.
    next: Optional[str] = None
    # Attribute requirements to view this scene.
    condition: Dict[str, Any] = field(default_factory=dict)

    def is_available(self, attributes: Dict[str, float]) -> bool:
        """A scene gated by attributes cannot be viewed without them."""
        probe = Choice(id="__scene__", conditions=self.condition)
        return probe.is_available(attributes)


@dataclass
class EndingRule:
    """An ending plus the requirements that unlock it."""

    id: str
    title: str = ""
    description: str = ""
    conditions: Dict[str, Any] = field(default_factory=dict)
    required_choices: List[str] = field(default_factory=list)
    hidden: bool = False
    priority: int = 0

    def is_reached(self, attributes: Dict[str, float], choice_history: List[str]) -> bool:
        probe = Choice(id="__ending__", conditions=self.conditions)
        if not probe.is_available(attributes):
            return False
        return all(choice_id in choice_history for choice_id in self.required_choices)


@dataclass
class EndingResult:
    """The outcome of calculate_ending, including a review of the run."""

    id: str
    title: str
    description: str
    hidden: bool
    review: str


class VisualNovelSystem:
    DEFAULT_MAX_SLOTS = 3

    def __init__(self, max_slots: int = DEFAULT_MAX_SLOTS):
        self.state: Dict[str, Any] = {}
        self.max_slots = max_slots
        self.attributes: Dict[str, float] = {}
        self.attribute_bounds: Dict[str, Dict[str, float]] = {}
        self.scenes: Dict[str, Scene] = {}
        self.choices: Dict[str, Choice] = {}
        self.endings: Dict[str, EndingRule] = {}
        self.choice_history: List[str] = []
        self.current_scene: Optional[str] = None
        self.save_slots: Dict[int, Dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Attributes: bounded, effective, and displayable
    # ------------------------------------------------------------------
    def register_attribute(self, name: str, initial: float = 0,
                           min_value: float = 0, max_value: float = 100) -> None:
        self.attribute_bounds[name] = {"min": min_value, "max": max_value}
        self.attributes[name] = self._clamp(name, initial)

    def _clamp(self, name: str, value: float) -> float:
        bounds = self.attribute_bounds.get(name)
        if not bounds:
            return value
        return max(bounds["min"], min(bounds["max"], value))

    def update_attribute(self, name: Optional[str] = None, delta: float = 0) -> Dict[str, float]:
        """Change an attribute, clamped to its bounds, and return all attributes.

        Attributes drive the game: choice conditions, scene conditions, and
        endings all read these values, so a change here affects what the
        player can do and see next.
        """
        if name is not None:
            if name not in self.attribute_bounds:
                self.register_attribute(name)
            self.attributes[name] = self._clamp(name, self.attributes.get(name, 0) + delta)
        return dict(self.attributes)

    def get_attribute(self, name: str) -> float:
        return self.attributes.get(name, 0)

    def get_attributes(self) -> Dict[str, float]:
        return dict(self.attributes)

    def display_attributes(self) -> str:
        """Human-readable display of current attributes for the player."""
        if not self.attributes:
            return "No attributes"
        return "\n".join(f"{name}: {value}" for name, value in sorted(self.attributes.items()))

    # ------------------------------------------------------------------
    # Story: scenes, branches, jumps, and conditions
    # ------------------------------------------------------------------
    def add_scene(self, scene_id: str, text: str = "",
                  choices: Optional[List[Choice]] = None,
                  next: Optional[str] = None,
                  condition: Optional[Dict[str, Any]] = None,
                  set_current: bool = False) -> Scene:
        scene = Scene(id=scene_id, text=text, next=next, condition=condition or {})
        for choice in choices or []:
            self.add_choice(choice, scene_id=scene_id)
            scene.choices.append(choice)
        self.scenes[scene_id] = scene
        if set_current or self.current_scene is None:
            self.current_scene = scene_id
        return scene

    def add_choice(self, choice: Choice, scene_id: Optional[str] = None) -> Choice:
        choice.scene = scene_id if scene_id is not None else choice.scene
        self.choices[choice.id] = choice
        if choice.scene and choice.scene in self.scenes:
            scene = self.scenes[choice.scene]
            if choice not in scene.choices:
                scene.choices.append(choice)
        return choice

    def get_current_scene(self) -> Optional[Scene]:
        if self.current_scene is None:
            return None
        return self.scenes.get(self.current_scene)

    def available_choices(self, scene_id: Optional[str] = None) -> List[Choice]:
        """Choices in the scene whose attribute conditions are met."""
        scene_id = scene_id or self.current_scene
        scene = self.scenes.get(scene_id) if scene_id else None
        if scene is None:
            return []
        return [c for c in scene.choices if c.is_available(self.attributes)]

    def advance_story(self, scene_id: Optional[str] = None) -> Optional[Scene]:
        """Move the story to a scene, following branches and enforcing conditions.

        With no argument, follows the current scene's default next scene.
        Returns the scene now being shown, or None if there is nowhere to go.
        """
        target_id = scene_id or (self.scenes[self.current_scene].next
                                 if self.current_scene in self.scenes else None)
        if target_id is None:
            return None
        scene = self.scenes.get(target_id)
        if scene is None:
            raise KeyError(f"Unknown scene: {target_id}")
        if not scene.is_available(self.attributes):
            raise ChoiceError(
                f"Scene '{target_id}' requires attributes the player does not have")
        self.current_scene = target_id
        return scene

    # ------------------------------------------------------------------
    # Choices: recorded, conditional, unique, and branching
    # ------------------------------------------------------------------
    def make_choice(self, choice_id: Optional[str] = None) -> Dict[str, Any]:
        """Make a choice: check conditions and uniqueness, record it, apply
        its attribute effects, and jump to its target scene if it has one."""
        if choice_id is None:
            return {
                "choice": None,
                "history": list(self.choice_history),
                "attributes": dict(self.attributes),
                "scene": self.current_scene,
            }
        choice = self.choices.get(choice_id)
        if choice is None:
            raise ChoiceError(f"Unknown choice: {choice_id}")
        if not choice.is_available(self.attributes):
            raise ChoiceError(
                f"Choice '{choice_id}' is locked: attribute conditions not met")
        if choice.unique and choice_id in self.choice_history:
            raise ChoiceError(f"Choice '{choice_id}' is unique and was already made")

        # Branch record: every choice is remembered and shapes what follows.
        self.choice_history.append(choice_id)
        for name, delta in choice.effects.items():
            self.update_attribute(name, delta)

        # Branch jump: a choice with a target moves the story to that scene.
        if choice.target is not None:
            self.advance_story(choice.target)

        return {
            "choice": choice,
            "history": list(self.choice_history),
            "attributes": dict(self.attributes),
            "scene": self.current_scene,
        }

    def get_choice_history(self) -> List[str]:
        return list(self.choice_history)

    # ------------------------------------------------------------------
    # Saves: slots storing choice history and story position
    # ------------------------------------------------------------------
    def save_game(self, slot: int = 0) -> Dict[str, Any]:
        """Save the full run state (choice history + story position) to a slot."""
        if not 0 <= slot < self.max_slots:
            raise SaveSlotError(f"Invalid save slot: {slot}")
        save = {
            "slot": slot,
            "choice_history": list(self.choice_history),
            "current_scene": self.current_scene,
            "attributes": dict(self.attributes),
            "attribute_bounds": copy.deepcopy(self.attribute_bounds),
        }
        self.save_slots[slot] = save
        return copy.deepcopy(save)

    def load_game(self, slot: int = 0) -> Dict[str, Any]:
        """Restore a run from a slot, including what was chosen and where."""
        if slot not in self.save_slots:
            raise SaveSlotError(f"Save slot {slot} is empty")
        save = self.save_slots[slot]
        self.choice_history = list(save["choice_history"])
        self.current_scene = save["current_scene"]
        self.attributes = dict(save["attributes"])
        self.attribute_bounds = copy.deepcopy(save["attribute_bounds"])
        return copy.deepcopy(save)

    def list_saves(self) -> List[int]:
        return sorted(self.save_slots)

    # ------------------------------------------------------------------
    # Endings: attribute-based, hidden, with a review
    # ------------------------------------------------------------------
    def register_ending(self, ending_id: str, title: str = "", description: str = "",
                        conditions: Optional[Dict[str, Any]] = None,
                        required_choices: Optional[List[str]] = None,
                        hidden: bool = False, priority: int = 0) -> EndingRule:
        rule = EndingRule(id=ending_id, title=title, description=description,
                          conditions=conditions or {},
                          required_choices=required_choices or [],
                          hidden=hidden, priority=priority)
        self.endings[ending_id] = rule
        return rule

    def _default_endings(self) -> List[EndingRule]:
        return [
            EndingRule(id="good", title="Good Ending", priority=10,
                       conditions={"affection": 50},
                       description="Your bond was strong enough."),
            EndingRule(id="bad", title="Bad Ending", priority=0,
                       conditions={"affection": {"max": 49}},
                       description="Your bond was not strong enough."),
        ]

    def available_endings(self, include_hidden: bool = False) -> List[str]:
        """Endings the player could discover; hidden ones stay secret."""
        rules = list(self.endings.values()) or self._default_endings()
        return [r.id for r in rules if include_hidden or not r.hidden]

    def calculate_ending(self) -> EndingResult:
        """Pick the ending the player's attributes and choices unlock.

        The highest-priority reached ending wins; hidden endings are only
        reachable through their specific requirements. The result includes a
        review explaining why this ending happened.
        """
        rules = list(self.endings.values()) or self._default_endings()
        reached = [r for r in rules if r.is_reached(self.attributes, self.choice_history)]
        if not reached:
            ending = EndingRule(id="normal", title="Normal Ending",
                                description="The story simply ended.")
        else:
            ending = max(reached, key=lambda r: r.priority)
        return EndingResult(id=ending.id, title=ending.title,
                            description=ending.description, hidden=ending.hidden,
                            review=self.review_ending(ending))

    def review_ending(self, ending: Optional[EndingRule] = None) -> str:
        """Explain why the player got this ending."""
        if ending is None:
            result = self.calculate_ending()
            ending = self.endings.get(result.id, EndingRule(id=result.id, title=result.title))
        lines = [f"Ending: {ending.title or ending.id}"]
        if self.attributes:
            lines.append("Final attributes: "
                         + ", ".join(f"{k}={v}" for k, v in sorted(self.attributes.items())))
        if self.choice_history:
            lines.append("Key choices: " + ", ".join(self.choice_history))
        unmet = []
        for name, requirement in ending.conditions.items():
            value = self.attributes.get(name, 0)
            if isinstance(requirement, dict):
                if "min" in requirement and value < requirement["min"]:
                    unmet.append(f"{name} needed >= {requirement['min']} (was {value})")
                if "max" in requirement and value > requirement["max"]:
                    unmet.append(f"{name} needed <= {requirement['max']} (was {value})")
            elif value < requirement:
                unmet.append(f"{name} needed >= {requirement} (was {value})")
        if unmet:
            lines.append("Unmet requirements: " + "; ".join(unmet))
        return "\n".join(lines)
