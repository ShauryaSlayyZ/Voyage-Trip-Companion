"""
Solver execution and result formatting.
"""

from ortools.sat.python import cp_model


def solve_and_print_results(model, visit, start, end, pois, budget_cap):
    """
    Solve the model and print formatted results.
    
    Args:
        model: The CP-SAT model to solve
        visit: Dictionary of visit decision variables
        start: Dictionary of start time variables
        end: Dictionary of end time variables
        pois: List of POI dictionaries
        budget_cap: Budget constraint value for display
        
    Returns:
        True if solution found, False otherwise
    """
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        print("=" * 60)
        print("POI OPTIMIZATION RESULTS")
        print("=" * 60)
        print(f"\nTotal POIs visited: {int(solver.ObjectiveValue())}")
        
        total_cost_value = sum(
            pois[i]['cost'] for i in range(len(pois)) if solver.Value(visit[i])
        )
        print(f"Total cost: ${total_cost_value} (Budget: ${budget_cap})")
        print("\nVisited POIs:\n")
        
        visited_pois = []
        for i, poi in enumerate(pois):
            if solver.Value(visit[i]):
                start_minutes = solver.Value(start[i])
                hours = start_minutes // 60
                minutes = start_minutes % 60
                visited_pois.append({
                    'name': poi['name'],
                    'start_time': f"{hours:02d}:{minutes:02d}",
                    'duration': poi['duration'],
                    'cost': poi['cost'],
                    'mandatory': poi['mandatory']
                })
        
        # Sort by start time for better readability
        visited_pois.sort(key=lambda x: x['start_time'])
        
        for poi_info in visited_pois:
            mandatory_flag = " [MANDATORY]" if poi_info['mandatory'] else ""
            print(f"  • {poi_info['name']}{mandatory_flag}")
            print(f"    Start: {poi_info['start_time']}")
            print(f"    Duration: {poi_info['duration']} minutes")
            print(f"    Cost: ${poi_info['cost']}")
            print()
        
        print("=" * 60)
        return True
    else:
        print("No solution found!")
        return False
