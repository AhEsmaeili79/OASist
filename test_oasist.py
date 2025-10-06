"""
Basic tests for OASist package
"""
import pytest
import sys
from pathlib import Path

# Add the package to Python path
sys.path.insert(0, str(Path(__file__).parent))

from oasist.oasist import main


def test_import():
    """Test that the package can be imported"""
    import oasist
    assert hasattr(oasist, 'oasist')


def test_version():
    """Test that version is accessible"""
    from oasist import __version__
    assert __version__ is not None
    assert isinstance(__version__, str)


def test_main_function_exists():
    """Test that main function exists"""
    assert callable(main)


if __name__ == "__main__":
    pytest.main([__file__])
