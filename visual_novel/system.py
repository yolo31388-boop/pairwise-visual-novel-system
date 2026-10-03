"""
pairwise-visual-novel-system - VisualNovelSystem

A branching visual novel engine core:

- Choices are recorded per branch, gated by attribute conditions, and may be
  unique so important decisions cannot be repeated.
- Attributes affect available choices/scenes/endings, are clamped to
  registered min/max bounds, and can be shown to the player.
- Scenes form a branching graph with explicit jumps and entry conditions.
- Save slots persist choice history and the current story position.
- Endings are decided by attributes and choices, include hidden endings, and
  produce a review explaining why an ending was reached.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


class ChoiceError(Exception):
    """Raised when a choice or scene transition is not allowed."""


class SaveSlotError(Exception):
    """Raised when a save slot is out of range or empty."""


def _meets_conditions(conditions: Dict[str, Any],
                      attributes: Dict[str, float]) -> bool:
    """Check attributes against requirement specs.

    A plain number means "at least" (e.g. {"affection": 50}); a mapping may
    give an explicit "min" and/or "max".
    """
    for name, requirement in conditions.items():
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
class Choice:
    """A selectable option inside a scene."""

    id: str
    text: str = ""
    conditions: Dict[str, Any] = field(default_factory=dict)
    effects: Dict[str, float] = field(default_factory=dict)
    target: Optional[str] = None
    unique: bool = False
    scene: Optional[str] = None

    def is_available(self, attributes: Dict[str, float]) -> bool:
        return _meets_conditions(self.conditions, attributes)


@dataclass
class Scene:
    """A story node with text, choices, an entry condition and a default next."""

    id: str
    text: str = ""
    choices: List[Choice] = field(default_factory=list)
    next: Optional[str] = None
    condition: Dict[str, Any] = field(default_factory=dict)

    def is_available(self, attributes: Dict[str, float]) -> bool:
        return _meets_conditions(self.condition, attributes)


@dataclass
class EndingRule:
    """An ending and the attributes / choices required to reach it."""

    id: str
    title: str = ""
    description: str = ""
    conditions: Dict[str, Any] = field(default_factory=dict)
    required_choices: List[str] = field(default_factory=list)
    hidden: bool = False
    priority: int = 0

    def is_reached(self, attributes: Dict[str, float],
                   choice_history: List[str]) -> bool:
        if not _meets_conditions(self.conditions, attributes):
            return False
        return all(choice_id in choice_history
                   for choice_id in self.required_choices)


@dataclass
class EndingResult:
    """An ending handed back to the player, with a recap of the run."""

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
    # Attributes
    # ------------------------------------------------------------------
    def register_attribute(self, name: str, initial: float = 0,
                           min_value: float = 0,
                           max_value: float = 100) -> None:
        self.attribute_bounds[name] = {"min": min_value, "max": max_value}
        self.attributes[name] = self._clamp(name, initial)

    def _clamp(self, name: str, value: float) -> float:
        bounds = self.attribute_bounds.get(name)
        if bounds is None:
            return value
        return max(bounds["min"], min(bounds["max"], value))

    def update_attribute(self, name: Optional[str] = None,
                         delta: float = 0) -> Dict[str, float]:
        """Apply a delta to an attribute, clamped to its registered bounds.

        Attribute values drive choice conditions, scene conditions and
        endings, so updating them changes what the player can do and see.
        """
        if name is not None:
            if name not in self.attribute_bounds:
                self.register_attribute(name)
            new_value = self.attributes.get(name, 0) + delta
            self.attributes[name] = self._clamp(name, new_value)
        return dict(self.attributes)

    def get_attribute(self, name: str) -> float:
        return self.attributes.get(name, 0)

    def get_attributes(self) -> Dict[str, float]:
        return dict(self.attributes)

    def display_attributes(self) -> str:
        """Return a human-readable view of the player's current attributes."""
        if not self.attributes:
            return "No attributes"
        return "\n".join(f"{name}: {value}"
                         for name, value in sorted(self.attributes.items()))

    # ------------------------------------------------------------------
    # Story graph
    # ------------------------------------------------------------------
    def add_scene(self, scene_id: str, text: str = "",
                  choices: Optional[List[Choice]] = None,
                  next: Optional[str] = None,
                  condition: Optional[Dict[str, Any]] = None,
                  set_current: bool = False) -> Scene:
        scene = Scene(id=scene_id, text=text, next=next,
                      condition=condition or {})
        for choice in choices or []:
            self.add_choice(choice, scene_id=scene_id)
            scene.choices.append(choice)
        self.scenes[scene_id] = scene
        if set_current or self.current_scene is None:
            self.current_scene = scene_id
        return scene

    def add_choice(self, choice: Choice,
                   scene_id: Optional[str] = None) -> Choice:
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

    def available_choices(self,
                          scene_id: Optional[str] = None) -> List[Choice]:
        """Choices offered in a scene whose conditions are currently met."""
        scene_id = scene_id if scene_id is not None else self.current_scene
        scene = self.scenes.get(scene_id) if scene_id is not None else None
        if scene is None:
            return []
        return [choice for choice in scene.choices
                if choice.is_available(self.attributes)]

    def advance_story(self,
                      scene_id: Optional[str] = None) -> Optional[Scene]:
        """Jump to a scene (or follow the current scene's default next).

        Scenes with unmet attribute conditions cannot be viewed. Returns the
        scene now shown, or None when there is nowhere to go.
        """
        if scene_id is None:
            current = self.scenes.get(self.current_scene) if self.current_scene else None
            target_id = current.next if current is not None else None
        else:
            target_id = scene_id
        if target_id is None:
            return None
        scene = self.scenes.get(target_id)
        if scene is None:
            raise KeyError(f"Unknown scene: {target_id}")
        if not scene.is_available(self.attributes):
            raise ChoiceError(
                f"Scene '{target_id}' is locked by unmet conditions")
        self.current_scene = target_id
        return scene

    # ------------------------------------------------------------------
    # Choices
    # ------------------------------------------------------------------
    def make_choice(self, choice_id: Optional[str] = None) -> Dict[str, Any]:
        """Record a branch choice, apply effects, and jump to its target.

        Raises ChoiceError for unknown choices, condition-locked choices, or
        repeated unique choices.
        """
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
                f"Choice '{choice_id}' is locked: conditions not met")
        if choice.unique and choice_id in self.choice_history:
            raise ChoiceError(
                f"Choice '{choice_id}' is unique and was already made")

        self.choice_history.append(choice_id)
        for name, delta in choice.effects.items():
            self.update_attribute(name, delta)

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
    # Save slots
    # ------------------------------------------------------------------
    def save_game(self, slot: int = 0) -> Dict[str, Any]:
        """Persist choice history, story position and attributes to a slot."""
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
        """Restore choice history and story position from a save slot."""
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
    # Endings
    # ------------------------------------------------------------------
    def register_ending(self, ending_id: str, title: str = "",
                        description: str = "",
                        conditions: Optional[Dict[str, Any]] = None,
                        required_choices: Optional[List[str]] = None,
                        hidden: bool = False,
                        priority: int = 0) -> EndingRule:
        rule = EndingRule(
            id=ending_id, title=title, description=description,
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
        """Discoverable ending ids; hidden endings stay secret by default."""
        rules = list(self.endings.values()) or self._default_endings()
        return [rule.id for rule in rules
                if include_hidden or not rule.hidden]

    def calculate_ending(self) -> EndingResult:
        """Choose the highest-priority ending unlocked by the run.

        Attributes and required choices are both checked; hidden endings are
        only reached through their own requirements. The result reviews why.
        """
        rules = list(self.endings.values()) or self._default_endings()
        reached = [rule for rule in rules
                   if rule.is_reached(self.attributes, self.choice_history)]
        if reached:
            ending = max(reached, key=lambda rule: rule.priority)
        else:
            ending = EndingRule(id="normal", title="Normal Ending",
                                description="The story simply ended.")
        return EndingResult(
            id=ending.id, title=ending.title,
            description=ending.description, hidden=ending.hidden,
            review=self.review_ending(ending))

    def review_ending(self, ending: Optional[EndingRule] = None) -> str:
        """Explain why the player reached this ending."""
        if ending is None:
            result = self.calculate_ending()
            ending = EndingRule(id=result.id, title=result.title)
        lines = [f"Ending: {ending.title or ending.id}"]
        if self.attributes:
            lines.append(
                "Final attributes: "
                + ", ".join(f"{name}={value}"
                            for name, value in sorted(self.attributes.items())))
        if self.choice_history:
            lines.append("Key choices: " + ", ".join(self.choice_history))
        unmet = []
        for name, requirement in ending.conditions.items():
            value = self.attributes.get(name, 0)
            if isinstance(requirement, dict):
                if "min" in requirement and value < requirement["min"]:
                    unmet.append(
                        f"{name} needed >= {requirement['min']} (was {value})")
                if "max" in requirement and value > requirement["max"]:
                    unmet.append(
                        f"{name} needed <= {requirement['max']} (was {value})")
            elif value < requirement:
                unmet.append(
                    f"{name} needed >= {requirement} (was {value})")
        if unmet:
            lines.append("Unmet requirements: " + "; ".join(unmet))
        return "\n".join(lines)
