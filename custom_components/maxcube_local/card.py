"""The weekly-programme Lovelace card: served from the integration, no manual resource needed."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CARD_FILE = Path(__file__).parent / "frontend" / "maxcube-schedule-card.js"
CARD_URL = f"/{DOMAIN}/maxcube-schedule-card.js"


async def async_register_card(hass: HomeAssistant) -> None:
    """Serve the card file and load it in every dashboard (once per Home Assistant start).

    The card is a convenience: if it cannot be registered, the integration still works.
    """
    # Imported here: the frontend component is only loaded when it is needed (and it is a
    # declared dependency, so it is set up before this runs).
    from homeassistant.components import frontend  # noqa: PLC0415

    try:
        integration = await async_get_integration(hass, DOMAIN)
        await hass.http.async_register_static_paths(
            [StaticPathConfig(CARD_URL, str(CARD_FILE), cache_headers=False)]
        )
        # The version in the query string makes browsers fetch the new file after an update.
        frontend.add_extra_js_url(hass, f"{CARD_URL}?v={integration.version}")
    except Exception:
        _LOGGER.warning("Could not register the weekly-programme card", exc_info=True)
