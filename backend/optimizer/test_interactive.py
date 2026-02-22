"""
Interactive Re-optimization Test

Allows users to:
1. View original optimized itinerary
2. Choose disruption type and intensity
3. See re-optimized itinerary
4. Compare changes
"""

from ortools.sat.python import cp_model
from data import POIS, TRAVEL_TIME, BUDGET_CAP, PLANNING_HORIZON
from model import build_poi_model


def print_separator():
    print("\n" + "="*70)


def print_itinerary(visit_values, start_values, pois, title="Itinerary"):
    """Print itinerary in a readable format."""
    print_separator()
    print(f"  {title}")
    print_separator()
    
    visited = []
    for i, poi in enumerate(pois):
        if visit_values[i]:
            start_min = start_values[i]
            hours = start_min // 60
            minutes = start_min % 60
            visited.append({
                'id': i,
                'name': poi['name'],
                'start_min': start_min,
                'start': f"{hours:02d}:{minutes:02d}",
                'duration': poi['duration'],
                'cost': poi['cost'],
                'mandatory': poi.get('mandatory', False)
            })
    
    visited.sort(key=lambda x: x['start_min'])
    
    total_cost = sum(p['cost'] for p in visited)
    print(f"\n  📊 Summary:")
    print(f"     Total POIs: {len(visited)}")
    print(f"     Total Cost: ${total_cost} / ${BUDGET_CAP}")
    
    print(f"\n  📅 Schedule:")
    for p in visited:
        mandatory = " 🔒 MANDATORY" if p['mandatory'] else ""
        print(f"     {p['start']} - {p['name']} ({p['duration']} min, ${p['cost']}){mandatory}")
    print()


def solve_and_get_values(model, visit, start, pois):
    """Solve model and return visit/start values."""
    solver = cp_model.CpSolver()
    solver.parameters.log_search_progress = False
    status = solver.Solve(model)
    
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        visit_values = [solver.Value(visit[i]) for i in range(len(pois))]
        start_values = [solver.Value(start[i]) for i in range(len(pois))]
        return visit_values, start_values, True
    else:
        return None, None, False


def get_disruption_choice():
    """Get user's disruption type choice."""
    print_separator()
    print("  ⚠️  DISRUPTION MENU")
    print_separator()
    print("\n  Choose a disruption type:")
    print("     1. 🌧️  Weather Alert (affects outdoor POIs)")
    print("     2. 👥 Crowd Surge (affects popular POIs)")
    print("     3. 🚗 Traffic Jam (increases travel time)")
    print("     4. 💰 Budget Reduction")
    print("     5. 🎨 Custom Disruption")
    print("     0. No Disruption (exit)")
    
    while True:
        try:
            choice = int(input("\n  Enter choice (0-5): "))
            if 0 <= choice <= 5:
                return choice
            print("  ❌ Invalid choice. Please enter 0-5.")
        except ValueError:
            print("  ❌ Invalid input. Please enter a number.")


def get_intensity():
    """Get disruption intensity from user."""
    print("\n  Choose disruption intensity:")
    print("     1. Mild")
    print("     2. Moderate")
    print("     3. Severe")
    
    while True:
        try:
            choice = int(input("\n  Enter intensity (1-3): "))
            if 1 <= choice <= 3:
                return choice
            print("  ❌ Invalid choice. Please enter 1-3.")
        except ValueError:
            print("  ❌ Invalid input. Please enter a number.")


def apply_weather_disruption(intensity):
    """Apply weather disruption based on intensity."""
    base_weather = [2, 8, 1, 3, 2]  # Original from data.py
    
    if intensity == 1:  # Mild
        return [2, 10, 1, 3, 2]  # Park slightly worse
    elif intensity == 2:  # Moderate
        return [2, 12, 1, 3, 2]  # Park moderately worse
    else:  # Severe
        return [2, 18, 2, 4, 2]  # Park severely worse
    

def apply_crowd_disruption(intensity):
    """Apply crowd surge disruption."""
    base_crowd = [8, 3, 6, 5, 9]  # Original from data.py
    
    if intensity == 1:  # Mild
        return [9, 4, 7, 6, 10]  # Slight increase everywhere
    elif intensity == 2:  # Moderate
        return [10, 5, 8, 7, 12]  # Moderate increase
    else:  # Severe
        return [12, 6, 10, 9, 15]  # Severe crowds everywhere


def apply_traffic_disruption(intensity, travel_time_base):
    """Apply traffic disruption (increases travel times)."""
    import copy
    travel_time = copy.deepcopy(travel_time_base)
    
    multiplier = 1.0 + (intensity * 0.3)  # 1.3x, 1.6x, 1.9x
    
    for i in range(len(travel_time)):
        for j in range(len(travel_time[i])):
            if i != j:
                travel_time[i][j] = int(travel_time[i][j] * multiplier)
    
    return travel_time


def apply_budget_disruption(intensity, budget_base):
    """Apply budget reduction."""
    reduction = intensity * 10  # -10, -20, -30
    return max(20, budget_base - reduction)


def show_comparison(orig_visit, orig_start, new_visit, new_start, pois, disruption_info):
    """Show detailed comparison of changes."""
    print_separator()
    print("  📊 CHANGE ANALYSIS")
    print_separator()
    
    if disruption_info:
        print(f"\n  Disruption Applied: {disruption_info}")
    
    changes_detected = False
    
    print("\n  Changes:")
    for i, poi in enumerate(pois):
        was_visited = orig_visit[i]
        is_visited = new_visit[i]
        
        if was_visited and not is_visited:
            print(f"     ❌ DROPPED: {poi['name']}")
            changes_detected = True
        elif not was_visited and is_visited:
            print(f"     ✅ ADDED: {poi['name']}")
            changes_detected = True
        elif was_visited and is_visited:
            old_time = orig_start[i]
            new_time = new_start[i]
            if old_time != new_time:
                shift = abs(new_time - old_time)
                old_h, old_m = old_time // 60, old_time % 60
                new_h, new_m = new_time // 60, new_time % 60
                direction = "later" if new_time > old_time else "earlier"
                print(f"     🔄 TIME SHIFT: {poi['name']}")
                print(f"        {old_h:02d}:{old_m:02d} → {new_h:02d}:{new_m:02d} ({shift} min {direction})")
                changes_detected = True
    
    if not changes_detected:
        print("     ℹ️  No changes needed")
    
    print(f"\n  Summary:")
    print(f"     Original POIs: {sum(orig_visit)}")
    print(f"     Re-optimized POIs: {sum(new_visit)}")
    print()


def main():
    print("\n" + "="*70)
    print("  🧪 INTERACTIVE RE-OPTIMIZATION TEST")
    print("="*70)
    
    # Generate original itinerary
    print("\n  📅 Generating original itinerary...")
    
    model_orig, visit_orig, start_orig, end_orig, interval_orig = build_poi_model(
        POIS, TRAVEL_TIME, BUDGET_CAP, PLANNING_HORIZON
    )
    
    orig_visit, orig_start, success = solve_and_get_values(
        model_orig, visit_orig, start_orig, POIS
    )
    
    if not success:
        print("  ❌ Failed to generate original itinerary!")
        return
    
    print_itinerary(orig_visit, orig_start, POIS, "✅ ORIGINAL ITINERARY")
    
    # Interactive loop
    while True:
        choice = get_disruption_choice()
        
        if choice == 0:
            print("\n  👋 Exiting test. Goodbye!\n")
            break
        
        # Get intensity
        intensity = get_intensity()
        intensity_labels = ["Mild", "Moderate", "Severe"]
        intensity_label = intensity_labels[intensity - 1]
        
        # Apply disruption
        disruption_info = ""
        crowd_level = [8, 3, 6, 5, 9]
        weather_penalty = [2, 8, 1, 3, 2]
        travel_time = TRAVEL_TIME
        budget_cap = BUDGET_CAP
        
        if choice == 1:  # Weather
            weather_penalty = apply_weather_disruption(intensity)
            disruption_info = f"🌧️ Weather Alert ({intensity_label})"
            weather_sensitivity = 8.0
        elif choice == 2:  # Crowd
            crowd_level = apply_crowd_disruption(intensity)
            disruption_info = f"👥 Crowd Surge ({intensity_label})"
            weather_sensitivity = 3.0
        elif choice == 3:  # Traffic
            travel_time = apply_traffic_disruption(intensity, TRAVEL_TIME)
            disruption_info = f"🚗 Traffic Jam ({intensity_label})"
            weather_sensitivity = 3.0
        elif choice == 4:  # Budget
            budget_cap = apply_budget_disruption(intensity, BUDGET_CAP)
            disruption_info = f"💰 Budget Reduced to ${budget_cap} ({intensity_label})"
            weather_sensitivity = 3.0
        elif choice == 5:  # Custom
            print("\n  Custom disruption - modify data.py for advanced scenarios")
            continue
        
        # Re-optimize
        print(f"\n  🔄 Re-optimizing with {disruption_info}...")
        
        model_new, visit_new, start_new, end_new, interval_new = build_poi_model(
            POIS, travel_time, budget_cap, PLANNING_HORIZON,
            old_visit=orig_visit,
            old_start=orig_start,
            penalty_drop=100,
            penalty_shift=1,
            reward_visit=50,
            crowd_level=crowd_level,
            weather_penalty=weather_penalty,
            travel_fatigue_weight=0.5,
            crowd_sensitivity=5.0,
            weather_sensitivity=weather_sensitivity
        )
        
        new_visit, new_start, success = solve_and_get_values(
            model_new, visit_new, start_new, POIS
        )
        
        if not success:
            print("  ❌ Failed to re-optimize itinerary!")
            continue
        
        print_itinerary(new_visit, new_start, POIS, "✅ RE-OPTIMIZED ITINERARY")
        show_comparison(orig_visit, orig_start, new_visit, new_start, POIS, disruption_info)
        
        # Ask to continue
        print("\n  Press Enter to try another disruption, or Ctrl+C to exit...")
        try:
            input()
        except KeyboardInterrupt:
            print("\n\n  👋 Exiting test. Goodbye!\n")
            break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  👋 Test interrupted. Goodbye!\n")
