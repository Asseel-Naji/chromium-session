"""
Allow running the package as a module: python -m chromium_session
"""

from .cli import app

if __name__ == "__main__":
    app()
