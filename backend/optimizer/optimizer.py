"""
OR-Tools CP-SAT Optimizer for POI Scheduling - Main Entry Point
"""

from data import (POIS, TRAVEL_TIME, BUDGET_CAP, PLANNING_HORIZON,
                  OLD_VISIT, OLD_START, PENALTY_DROP_POI, 
                  PENALTY_TIME_SHIFT, REWARD_VISIT_POI,
                  CROWD_LEVEL, WEATHER_PENALTY, TRAVEL_FATIGUE_WEIGHT,
                  CROWD_SENSITIVITY, WEATHER_SENSITIVITY)
from model import build_poi_model
from solver import solve_and_print_results


def main(use_reoptimization=True, use_difficulty=True):
    """Main entry point for the POI optimizer.
    
    Args:
        use_reoptimization: If True, use re-optimization mode with old itinerary
        use_difficulty: If True, include difficulty-based penalties (crowd, weather, fatigue)
    """
    if use_reoptimization or use_difficulty:
        # Build model with penalties and/or difficulty
        model, visit, start, end, interval = build_poi_model(
            POIS, 
            TRAVEL_TIME, 
            BUDGET_CAP, 
            PLANNING_HORIZON,
            old_visit=OLD_VISIT if use_reoptimization else None,
            old_start=OLD_START if use_reoptimization else None,
            penalty_drop=PENALTY_DROP_POI if use_reoptimization else 0,
            penalty_shift=PENALTY_TIME_SHIFT if use_reoptimization else 0,
            reward_visit=REWARD_VISIT_POI,
            crowd_level=CROWD_LEVEL if use_difficulty else None,
            weather_penalty=WEATHER_PENALTY if use_difficulty else None,
            travel_fatigue_weight=TRAVEL_FATIGUE_WEIGHT if use_difficulty else 0,
            crowd_sensitivity=CROWD_SENSITIVITY if use_difficulty else 0,
            weather_sensitivity=WEATHER_SENSITIVITY if use_difficulty else 0
        )
        
        mode_str = []
        if use_reoptimization:
            mode_str.append("RE-OPTIMIZATION")
        if use_difficulty:
            mode_str.append("DIFFICULTY-BASED")
        print(f"🔄 {' + '.join(mode_str)} MODE")
        print("=" * 60)
    else:
        # Standard optimization mode
        model, visit, start, end, interval = build_poi_model(
            POIS, 
            TRAVEL_TIME, 
            BUDGET_CAP, 
            PLANNING_HORIZON
        )
        print("✨ STANDARD OPTIMIZATION MODE")
        print("=" * 60)
    
    # Solve and display results
    solve_and_print_results(
        model, visit, start, end, POIS, BUDGET_CAP,
        old_visit=OLD_VISIT if use_reoptimization else None,
        old_start=OLD_START if use_reoptimization else None
    )


if __name__ == "__main__":
    # Options: (use_reoptimization, use_difficulty)
    main(use_reoptimization=True, use_difficulty=True)  # Full mode with all features


