# Optimizer Test Suite

## test_disruption.py

Demonstrates re-optimization when a disruption occurs.

### Scenario

1. **Original Itinerary**: Generate optimal schedule with standard optimization
2. **Disruption**: Weather alert - heavy rain expected! Outdoor POIs heavily affected
3. **Re-optimization**: Adjust itinerary to minimize weather impact while keeping changes minimal
4. **Comparison**: Show what changed and why

### Running the Test

```bash
python test_disruption.py
```

### Expected Behavior

The test will:
- Show the original itinerary (4 POIs visited)
- Simulate a weather disruption (Park's weather penalty increases from 8 to 15)
- Re-optimize considering:
  - Penalty for dropping POIs from original plan
  - High weather sensitivity (avoid outdoor POIs)
  - Budget and time constraints
- Display changes:
  - ❌ DROPPED: Park (due to severe weather)
  - Other POIs rescheduled as needed

### Key Features Tested

✅ **Re-optimization** - Maintains stability from old itinerary  
✅ **Weather penalties** - Responds to weather disruptions  
✅ **Crowd sensitivity** - Considers crowd levels  
✅ **Travel fatigue** - Minimizes travel time  
✅ **Constraint satisfaction** - Respects budget, hours, mandatory POIs

### Configuring Disruption Intensity

Edit the `DISRUPTED_WEATHER` array in `test_disruption.py`:

```python
DISRUPTED_WEATHER = [
    2,   # Museum (indoor)
    15,  # Park (outdoor - HEAVILY AFFECTED)
    1,   # Restaurant (indoor)
    3,   # Art Gallery (indoor)
    2    # Shopping Mall (indoor)
]
```

Higher values = more severe weather impact
