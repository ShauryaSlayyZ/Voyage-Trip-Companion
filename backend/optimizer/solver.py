"""
Solver execution and result formatting.
"""

from ortools.sat.python import cp_model


def solve_and_print_results(model, visit, start, end, pois, budget_cap, 
                             old_visit=None, old_start=None):
    """
    Solve the model and print formatted results.
    
    Args:
        model: The CP-SAT model to solve
        visit: Dictionary of visit decision variables
        start: Dictionary of start time variables
        end: Dictionary of end time variables
        pois: List of POI dictionaries
        budget_cap: Budget constraint value for display
        old_visit: List of previous visit decisions (optional, for comparison)
        old_start: List of previous start times (optional, for comparison)
        
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
        
        # Show comparison with old itinerary if available
        if old_visit is not None and old_start is not None:
            print("\n📊 Changes from Old Itinerary:\n")
            
            for i, poi in enumerate(pois):
                was_visited = old_visit[i]
                is_visited = solver.Value(visit[i])
                
                if was_visited and not is_visited:
                    print(f"  ❌ DROPPED: {poi['name']}")
                elif not was_visited and is_visited:
                    print(f"  ✅ ADDED: {poi['name']}")
                elif was_visited and is_visited:
                    old_time = old_start[i]
                    new_time = solver.Value(start[i])
                    shift = abs(new_time - old_time)
                    if shift > 0:
                        old_h, old_m = old_time // 60, old_time % 60
                        new_h, new_m = new_time // 60, new_time % 60
                        direction = "later" if new_time > old_time else "earlier"
                        print(f"  🔄 SHIFTED: {poi['name']} - {old_h:02d}:{old_m:02d} → {new_h:02d}:{new_m:02d} ({shift} min {direction})")
        
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
