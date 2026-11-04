"""Home Assistant fixtures for the custom integration."""

import pytest


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    """Allow Home Assistant to load the local custom integration."""
