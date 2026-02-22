"""
Test script to demonstrate re-optimization with disruptions.

Scenario:
1. Start with an optimized itinerary (original plan)
2. Simulate a disruption (weather worsens at outdoor POIs)
3. Re-optimize the itinerary considering the disruption
4. Show comparison: original vs re-optimized
"""

from ortools.sat.python import cp_model
from data import POIS, TRAVEL_TIME, BUDGET_CAP, PLANNING_HORIZON
from model import build_poi_model
from solver import solve_and_print_results


def print_itinerary(visit_values, start_values, pois, title="Itinerary"):
    """Helper to print an itinerary in a readable format."""
    print(f"\n{'='*60}")
    print(f"{title}")
    print(f"{'='*60}")
    
    visited = []
    for i, poi in enumerate(pois):
        if visit_values[i]:
            start_min = start_values[i]
            hours = start_min // 60
            minutes = start_min % 60
            visited.append({
                'name': poi['name'],
                'start': f"{hours:02d}:{minutes:02d}",
                'duration': poi['duration'],
                'cost': poi['cost']
            })
    
    visited.sort(key=lambda x: x['start'])
    
    total_cost = sum(p['cost'] for p in visited)
    print(f"\nTotal POIs: {len(visited)}")
    print(f"Total Cost: ${total_cost}")
    print("\nSchedule:")
    for p in visited:
        print(f"  {p['start']} - {p['name']} ({p['duration']} min, ${p['cost']})")
    print()


def solve_and_get_values(model, visit, start, pois):
    """Solve model and return visit/start values."""
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        visit_values = [solver.Value(visit[i]) for i in range(len(pois))]
        start_values = [solver.Value(start[i]) for i in range(len(pois))]
        return visit_values, start_values, True
    else:
        return None, None, False


def main():
    print("\n" + "="*60)
    print("🧪 DISRUPTION RE-OPTIMIZATION TEST")
    print("="*60)
    
    # ========================================================================
    # STEP 1: Generate original itinerary (standard optimization)
    # ========================================================================
    print("\n📅 STEP 1: Generating Original Itinerary (Standard Mode)")
    print("-" * 60)
    
    model_orig, visit_orig, start_orig, end_orig, interval_orig = build_poi_model(
        POIS, TRAVEL_TIME, BUDGET_CAP, PLANNING_HORIZON
    )
    
    orig_visit, orig_start, success = solve_and_get_values(
        model_orig, visit_orig, start_orig, POIS
    )
    
    if not success:
        print("❌ Failed to generate original itinerary!")
        return
    
    print_itinerary(orig_visit, orig_start, POIS, "✅ Original Itinerary")
    
    # ========================================================================
    # STEP 2: Simulate disruption
    # ========================================================================
    print("\n⚠️  STEP 2: DISRUPTION DETECTED!")
    print("-" * 60)
    print("Weather alert: Heavy rain expected! 🌧️")
    print("Impact on outdoor POIs:")
    
    # Create disrupted weather penalties (outdoor POIs heavily penalized)
    DISRUPTED_WEATHER = [
        2,   # Museum (indoor, minimal impact)
        15,  # Park (outdoor, heavily affected!) 
        1,   # Restaurant (indoor, minimal impact)
        3,   # Art Gallery (indoor, minimal impact)
        2    # Shopping Mall (indoor, minimal impact)
    ]
    
    for i, poi in enumerate(POIS):
        if DISRUPTED_WEATHER[i] > 10:
            print(f"  ⚠️  {poi['name']}: Weather penalty {DISRUPTED_WEATHER[i]}/10 (severe)")
    
    # ========================================================================
    # STEP 3: Re-optimize with disruption
    # ========================================================================
    print("\n🔄 STEP 3: Re-optimizing Itinerary")
    print("-" * 60)
    print("Constraints:")
    print("  • Minimize changes from original plan")
    print("  • Avoid severely weather-affected POIs")
    print("  • Respect budget, opening hours, mandatory POIs")
    
    # Re-optimize with:
    # - Old itinerary to minimize changes
    # - Disrupted weather data
    # - High weather sensitivity
    model_new, visit_new, start_new, end_new, interval_new = build_poi_model(
        POIS, TRAVEL_TIME, BUDGET_CAP, PLANNING_HORIZON,
        old_visit=orig_visit,
        old_start=orig_start,
        penalty_drop=100,      # High penalty for dropping POIs
        penalty_shift=1,       # Penalty for time changes
        reward_visit=50,       # Reward for visiting POIs
        crowd_level=[8, 3, 6, 5, 9],  # Crowd levels (from data.py)
        weather_penalty=DISRUPTED_WEATHER,  # New disrupted weather!
        travel_fatigue_weight=0.5,
        crowd_sensitivity=5.0,
        weather_sensitivity=8.0  # High sensitivity to weather disruption!
    )
    
    new_visit, new_start, success = solve_and_get_values(
        model_new, visit_new, start_new, POIS
    )
    
    if not success:
        print("❌ Failed to re-optimize itinerary!")
        return
    
    print_itinerary(new_visit, new_start, POIS, "✅ Re-optimized Itinerary")
    
    # ========================================================================
    # STEP 4: Show detailed comparison
    # ========================================================================
    print("\n📊 STEP 4: Change Analysis")
    print("-" * 60)
    
    changes_detected = False
    
    for i, poi in enumerate(POIS):
        was_visited = orig_visit[i]
        is_visited = new_visit[i]
        
        if was_visited and not is_visited:
            print(f"  ❌ DROPPED: {poi['name']}")
            print(f"     Reason: Weather penalty too high ({DISRUPTED_WEATHER[i]}/10)")
            changes_detected = True
        elif not was_visited and is_visited:
            print(f"  ✅ ADDED: {poi['name']}")
            changes_detected = True
        elif was_visited and is_visited:
            old_time = orig_start[i]
            new_time = new_start[i]
            if old_time != new_time:
                shift = abs(new_time - old_time)
                old_h, old_m = old_time // 60, old_time % 60
                new_h, new_m = new_time // 60, new_time % 60
                direction = "later" if new_time > old_time else "earlier"
                print(f"  🔄 TIME SHIFT: {poi['name']}")
                print(f"     {old_h:02d}:{old_m:02d} → {new_h:02d}:{new_m:02d} ({shift} min {direction})")
                changes_detected = True
    
    if not changes_detected:
        print("  ℹ️  No changes needed - original itinerary optimal even with disruption")
    
    # Summary
    print("\n" + "="*60)
    print("🎯 TEST SUMMARY")
    print("="*60)
    print(f"Original POIs visited: {sum(orig_visit)}")
    print(f"Re-optimized POIs visited: {sum(new_visit)}")
    print(f"Changes made: {'Yes' if changes_detected else 'No'}")
    print("\n✅ Test completed successfully!")
    print("="*60)


if __name__ == "__main__":
    main()
