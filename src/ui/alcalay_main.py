# -*- coding: utf-8 -*-

"""
Alcalay - Application Entry Point
=================================

Main startup file for the Alcalay desktop application.

Location:
    src/ui/alcalay_main.py

Run from the project root:

    python src/ui/alcalay_main.py

Windows:

    python src\\ui\\alcalay_main.py
"""

from __future__ import annotations

import sys
from pathlib import Path


# ----------------------------------------------------------------------
# Project paths
# ----------------------------------------------------------------------

CURRENT_FILE = Path(__file__).resolve()

PROJECT_ROOT = CURRENT_FILE.parents[2]
SRC_ROOT = PROJECT_ROOT / "src"


# ----------------------------------------------------------------------
# Make src available for imports
# ----------------------------------------------------------------------

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


# ----------------------------------------------------------------------
# Qt imports
# ----------------------------------------------------------------------

from PySide6.QtWidgets import QApplication


# ----------------------------------------------------------------------
# Main window
# ----------------------------------------------------------------------

from ui.main_window import MainWindow


# ----------------------------------------------------------------------
# Application configuration
# ----------------------------------------------------------------------

APPLICATION_NAME = "Alcalay"
ORGANIZATION_NAME = "Alcalay"


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------

def main() -> int:
    """
    Start the Alcalay application.
    """

    app = QApplication.instance()

    if app is None:
        app = QApplication(sys.argv)

    app.setApplicationName(
        APPLICATION_NAME
    )

    app.setOrganizationName(
        ORGANIZATION_NAME
    )

    app.setApplicationDisplayName(
        "Alcalay - מערכת מידע"
    )

    # --------------------------------------------------------------
    # Create and display main window
    # --------------------------------------------------------------

    window = MainWindow()

    window.show()

    # --------------------------------------------------------------
    # Start Qt event loop
    # --------------------------------------------------------------

    return app.exec()


# ----------------------------------------------------------------------
# Direct execution
# ----------------------------------------------------------------------

if __name__ == "__main__":
    sys.exit(main())