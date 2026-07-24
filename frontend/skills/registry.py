"""Aggregated Skills Registry for Nexus AI Enterprise Workspace.

Combines all 78 verified skills across 7 specialized domain modules.
"""

from .design_tech import DESIGN_TECH_SKILLS
from .gtm_growth import GTM_GROWTH_SKILLS
from .pm_discovery import PM_DISCOVERY_SKILLS
from .pm_execution import PM_EXECUTION_SKILLS
from .pm_strategy import PM_STRATEGY_SKILLS
from .research_data import RESEARCH_DATA_SKILLS
from .toolkit_ai_ship import TOOLKIT_AI_SHIP_SKILLS

ALL_SKILLS = {
    **PM_STRATEGY_SKILLS,
    **PM_DISCOVERY_SKILLS,
    **PM_EXECUTION_SKILLS,
    **GTM_GROWTH_SKILLS,
    **RESEARCH_DATA_SKILLS,
    **TOOLKIT_AI_SHIP_SKILLS,
    **DESIGN_TECH_SKILLS,
}

__all__ = ["ALL_SKILLS"]
