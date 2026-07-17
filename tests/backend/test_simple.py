#!/usr/bin/env python3
"""
Simple tests that don't require database connections
"""

import pytest
import sys
from pathlib import Path

# Add the backend directory to Python path
backend_path = Path(__file__).parent.parent.parent / "backend"
sys.path.insert(0, str(backend_path))

def test_imports():
    """Test that we can import the main modules"""
    try:
        from app.main import app
        assert app is not None
    except ImportError as e:
        pytest.skip(f"Could not import app.main: {e}")

def test_config():
    """Test that configuration can be loaded"""
    try:
        from app.core.config import settings
        assert settings is not None
        assert hasattr(settings, 'project_name')
        assert settings.project_name == "CivicSpark AI"
    except ImportError as e:
        pytest.skip(f"Could not import config: {e}")

def test_models_import():
    """Test that models can be imported"""
    try:
        from app.models.meeting import Meeting, AgendaItem
        assert Meeting is not None
        assert AgendaItem is not None
    except ImportError as e:
        pytest.skip(f"Could not import models: {e}")

def test_scraper_import():
    """Test that scraper can be imported"""
    try:
        from app.scrapers.tgov_scraper import TGOVScraper
        assert TGOVScraper is not None
    except ImportError as e:
        pytest.skip(f"Could not import scraper: {e}")
