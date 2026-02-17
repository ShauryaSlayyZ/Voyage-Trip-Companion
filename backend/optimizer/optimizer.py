"""
OR-Tools CP-SAT Optimizer for POI Scheduling - Main Entry Point
"""

from data import POIS, TRAVEL_TIME, BUDGET_CAP, PLANNING_HORIZON
from model import build_poi_model
from solver import solve_and_print_results


def main():
    """Main entry point for the POI optimizer."""
    # Build the optimization model
    model, visit, start, end, interval = build_poi_model(
        POIS, 
        TRAVEL_TIME, 
        BUDGET_CAP, 
        PLANNING_HORIZON
    )
    
    # Solve and display results
    solve_and_print_results(model, visit, start, end, POIS, BUDGET_CAP)


if __name__ == "__main__":
    main()
