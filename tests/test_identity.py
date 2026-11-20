"""Tests for the title helpers (the title is generated from the serial number, never from the address)."""

from __future__ import annotations

import pytest

from maxcube_local import identity


def test_the_title_is_built_from_the_serial_number() -> None:
    assert identity.cube_title("JEQ0355273") == "MAX! Cube JEQ0355273"


@pytest.mark.parametrize(
    "title",
    ["MAX! Cube (192.168.10.60)", "MAX! Cube JEQ0355273", "MAX! Cube"],
)
def test_titles_made_by_the_integration_are_recognised(title: str) -> None:
    assert identity.is_generated_title(title)


@pytest.mark.parametrize(
    "title",
    ["Heizung Erdgeschoss", "MAX! Cube Keller", "MAX! Cube (x) extra", "my MAX! Cube (192.168.10.60)", ""],
)
def test_titles_chosen_by_the_user_are_left_alone(title: str) -> None:
    assert not identity.is_generated_title(title)
