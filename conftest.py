"""Shared pytest fixtures for the offline scraper tests."""

import pytest


@pytest.fixture
def play_cassette(request):
    """Placeholder so individual tests can opt into per-test cassettes."""
    return request.node.name
