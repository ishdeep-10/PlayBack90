"""Shots & SCA view module.

The shots/SCA builders currently live in app.services.matches because they are
also used by builders that remain there (build_shot_player_summary,
build_shot_details). This module re-exports the public view entry point so
routing code and future shots feature work can target app.services.views.shots.
"""

from app.services.matches import build_shots_sca_view

__all__ = ["build_shots_sca_view"]
