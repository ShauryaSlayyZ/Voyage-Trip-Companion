"""
CP-SAT model building logic for POI optimization.
"""

from ortools.sat.python import cp_model


def build_poi_model(pois, travel_time, budget_cap, planning_horizon):
    """
    Build the CP-SAT model for POI optimization.
    
    Args:
        pois: List of POI dictionaries with attributes
        travel_time: 2D matrix of travel times between POIs
        budget_cap: Maximum budget constraint
        planning_horizon: Maximum time in minutes for planning
        
    Returns:
        Tuple of (model, visit, start, end, interval) dictionaries
    """
    model = cp_model.CpModel()
    num_pois = len(pois)
    
    # Decision variables
    visit = {}  # Whether POI is visited
    start = {}  # Start time of each POI
    end = {}    # End time of each POI
    interval = {}  # Interval variable for each POI
    
    for i, poi in enumerate(pois):
        visit[i] = model.NewBoolVar(f'visit_{i}')
        start[i] = model.NewIntVar(0, planning_horizon, f'start_{i}')
        end[i] = model.NewIntVar(0, planning_horizon, f'end_{i}')
        
        # Optional interval: active only if visit[i] is True
        interval[i] = model.NewOptionalIntervalVar(
            start[i], 
            poi['duration'], 
            end[i], 
            visit[i], 
            f'interval_{i}'
        )
    
    # Constraint 1: Mandatory POIs must be visited
    for i, poi in enumerate(pois):
        if poi['mandatory']:
            model.Add(visit[i] == 1)
    
    # Constraint 2: Start time within opening hours (only if visited)
    for i, poi in enumerate(pois):
        model.Add(start[i] >= poi['opening_start']).OnlyEnforceIf(visit[i])
        model.Add(end[i] <= poi['opening_end']).OnlyEnforceIf(visit[i])
    
    # Constraint 3: Budget cap
    total_cost = sum(poi['cost'] * visit[i] for i, poi in enumerate(pois))
    model.Add(total_cost <= budget_cap)
    
    # Constraint 4: No overlap between visited POIs
    model.AddNoOverlap(interval.values())
    
    # Constraint 5: Travel time precedences
    for i in range(num_pois):
        for j in range(num_pois):
            if i != j:
                # Create a literal: does i come before j?
                i_before_j = model.NewBoolVar(f'precedes_{i}_{j}')
                
                # If both are visited, one must precede the other
                both_visited = model.NewBoolVar(f'both_visited_{i}_{j}')
                model.AddBoolAnd([visit[i], visit[j]]).OnlyEnforceIf(both_visited)
                
                # If i comes before j: end[i] + travel_time[i][j] <= start[j]
                model.Add(end[i] + travel_time[i][j] <= start[j]).OnlyEnforceIf(
                    [both_visited, i_before_j]
                )
                
                # If j comes before i: end[j] + travel_time[j][i] <= start[i]
                model.Add(end[j] + travel_time[j][i] <= start[i]).OnlyEnforceIf(
                    [both_visited, i_before_j.Not()]
                )
    
    # Objective: Maximize number of visited POIs
    model.Maximize(sum(visit[i] for i in range(num_pois)))
    
    return model, visit, start, end, interval
