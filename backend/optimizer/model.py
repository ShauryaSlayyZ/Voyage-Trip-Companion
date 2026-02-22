"""
CP-SAT model building logic for POI optimization.
"""

from ortools.sat.python import cp_model


def build_poi_model(pois, travel_time, budget_cap, planning_horizon, 
                     old_visit=None, old_start=None, 
                     penalty_drop=0, penalty_shift=0, reward_visit=0,
                     crowd_level=None, weather_penalty=None,
                     travel_fatigue_weight=0, crowd_sensitivity=0, weather_sensitivity=0):
    """
    Build the CP-SAT model for POI optimization with optional re-optimization support
    and difficulty-based objectives.
    
    Args:
        pois: List of POI dictionaries with attributes
        travel_time: 2D matrix of travel times between POIs
        budget_cap: Maximum budget constraint
        planning_horizon: Maximum time in minutes for planning
        old_visit: List of bools indicating previously visited POIs (optional)
        old_start: List of previous start times in minutes (optional)
        penalty_drop: Penalty weight for dropping a previously visited POI
        penalty_shift: Penalty weight per minute of time shift
        reward_visit: Reward for visiting a POI (balances penalties)
        crowd_level: List of crowd levels per POI (0-10 scale, optional)
        weather_penalty: List of weather penalties per POI (0-10 scale, optional)
        travel_fatigue_weight: Weight per minute of travel time
        crowd_sensitivity: Multiplier for crowd discomfort
        weather_sensitivity: Multiplier for weather discomfort
        
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
    
    # Objective: Maximize visits OR Minimize (penalties + difficulty) - rewards
    penalties = []
    
    # Re-optimization penalties
    if old_visit is not None and old_start is not None:
        for i in range(num_pois):
            # Penalty for dropping a previously visited POI
            if old_visit[i]:
                was_visited_now_dropped = model.NewBoolVar(f'dropped_{i}')
                model.Add(visit[i] == 0).OnlyEnforceIf(was_visited_now_dropped)
                model.Add(visit[i] == 1).OnlyEnforceIf(was_visited_now_dropped.Not())
                penalties.append(penalty_drop * was_visited_now_dropped)
            
            # Penalty for time shift: |start[i] - old_start[i]|
            if old_visit[i] and penalty_shift > 0:
                # Linearize absolute value using two variables
                time_shift_pos = model.NewIntVar(0, planning_horizon, f'shift_pos_{i}')
                time_shift_neg = model.NewIntVar(0, planning_horizon, f'shift_neg_{i}')
                
                # Only apply penalty if POI is visited in both old and new
                still_visited = model.NewBoolVar(f'still_visited_{i}')
                model.Add(visit[i] == 1).OnlyEnforceIf(still_visited)
                model.Add(visit[i] == 0).OnlyEnforceIf(still_visited.Not())
                
                # shift_pos - shift_neg = start[i] - old_start[i]
                model.Add(start[i] - old_start[i] == time_shift_pos - time_shift_neg).OnlyEnforceIf(still_visited)
                model.Add(time_shift_pos == 0).OnlyEnforceIf(still_visited.Not())
                model.Add(time_shift_neg == 0).OnlyEnforceIf(still_visited.Not())
                
                # Total shift = |shift| = pos + neg
                penalties.append(penalty_shift * (time_shift_pos + time_shift_neg))
    
    # Difficulty components
    if crowd_level is not None and weather_penalty is not None:
        for i in range(num_pois):
            # Crowd discomfort (only if visited)
            if crowd_sensitivity > 0:
                penalties.append(crowd_sensitivity * crowd_level[i] * visit[i])
            
            # Weather discomfort (only if visited)
            if weather_sensitivity > 0:
                penalties.append(weather_sensitivity * weather_penalty[i] * visit[i])
        
        # Travel fatigue (proportional to total travel time)
        if travel_fatigue_weight > 0:
            for i in range(num_pois):
                for j in range(num_pois):
                    if i != j:
                        # Create literal: does i immediately precede j?
                        i_precedes_j = model.NewBoolVar(f'i_precedes_j_{i}_{j}')
                        
                        # Both must be visited
                        both_visited = model.NewBoolVar(f'both_for_fatigue_{i}_{j}')
                        model.AddBoolAnd([visit[i], visit[j]]).OnlyEnforceIf(both_visited)
                        
                        # If i precedes j in sequence: end[i] + travel[i][j] <= start[j]
                        # This is already enforced, but we need to track when it happens
                        model.Add(end[i] + travel_time[i][j] == start[j]).OnlyEnforceIf(
                            [both_visited, i_precedes_j]
                        )
                        
                        # Add travel fatigue penalty when i precedes j
                        penalties.append(travel_fatigue_weight * travel_time[i][j] * i_precedes_j)
    
    # Rewards for visits (negative penalty = reward)
    if reward_visit > 0:
        for i in range(num_pois):
            penalties.append(-reward_visit * visit[i])
    
    # Choose objective based on whether we have penalties or difficulty
    if penalties:
        # Minimize total penalty + difficulty - rewards
        model.Minimize(sum(penalties))
    else:
        # Standard mode: maximize number of visited POIs
        model.Maximize(sum(visit[i] for i in range(num_pois)))
    
    return model, visit, start, end, interval


