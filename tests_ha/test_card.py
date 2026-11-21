"""The weekly-programme card is served by the integration and loaded in every dashboard."""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from homeassistant import components
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration
from homeassistant.setup import async_setup_component

from custom_components.maxcube_local import card
from custom_components.maxcube_local.const import DOMAIN


async def test_the_card_file_is_served_and_added_to_the_extra_js_urls(
    hass: HomeAssistant, hass_client_no_auth
) -> None:
    assert card.CARD_FILE.is_file()
    # The autouse fixture of conftest.py counts http as set up; here the real one is needed.
    if "http" in hass.config.components:
        hass.config.components.remove("http")
    assert await async_setup_component(hass, "http", {})
    frontend = MagicMock()
    with (
        patch.dict(sys.modules, {"homeassistant.components.frontend": frontend}),
        patch.object(components, "frontend", frontend, create=True),
    ):
        await card.async_register_card(hass)

    version = (await async_get_integration(hass, DOMAIN)).version
    frontend.add_extra_js_url.assert_called_once_with(
        hass, f"/{DOMAIN}/maxcube-schedule-card.js?v={version}"
    )
    client = await hass_client_no_auth()
    response = await client.get(f"/{DOMAIN}/maxcube-schedule-card.js")
    assert response.status == 200
    assert await response.read() == card.CARD_FILE.read_bytes()


async def test_a_failing_registration_does_not_break_the_integration(
    hass: HomeAssistant,
) -> None:
    hass.http = MagicMock()
    hass.http.async_register_static_paths.side_effect = RuntimeError("route exists")
    with patch.dict(sys.modules, {"homeassistant.components.frontend": MagicMock()}):
        await card.async_register_card(hass)  # logs a warning, raises nothing


async def test_the_integration_registers_the_card_once_at_setup(hass: HomeAssistant) -> None:
    with patch("custom_components.maxcube_local.async_register_card") as register:
        assert await async_setup_component(hass, DOMAIN, {})
    register.assert_awaited_once_with(hass)
