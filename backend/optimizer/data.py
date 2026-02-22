"""
POI dataset and travel time matrix configuration.
"""

# Hardcoded dataset of 5 POIs
POIS = [
    {
        'name': 'Museum',
        'duration': 120,  # minutes
        'cost': 15,
        'opening_start': 9 * 60,  # 9:00 AM in minutes
        'opening_end': 17 * 60,   # 5:00 PM in minutes
        'mandatory': True
    },
    {
        'name': 'Park',
        'duration': 90,
        'cost': 0,
        'opening_start': 6 * 60,  # 6:00 AM
        'opening_end': 20 * 60,   # 8:00 PM
        'mandatory': False
    },
    {
        'name': 'Restaurant',
        'duration': 60,
        'cost': 25,
        'opening_start': 11 * 60,  # 11:00 AM
        'opening_end': 22 * 60,    # 10:00 PM
        'mandatory': True
    },
    {
        'name': 'Art Gallery',
        'duration': 75,
        'cost': 10,
        'opening_start': 10 * 60,  # 10:00 AM
        'opening_end': 18 * 60,    # 6:00 PM
        'mandatory': False
    },
    {
        'name': 'Shopping Mall',
        'duration': 100,
        'cost': 30,
        'opening_start': 10 * 60,  # 10:00 AM
        'opening_end': 21 * 60,    # 9:00 PM
        'mandatory': False
    }
]

# Travel time matrix (minutes between POIs)
# Rows/Cols: Museum, Park, Restaurant, Art Gallery, Shopping Mall
TRAVEL_TIME = [
    [0, 15, 10, 12, 20],  # From Museum
    [15, 0, 25, 18, 30],  # From Park
    [10, 25, 0, 8, 15],   # From Restaurant
    [12, 18, 8, 0, 22],   # From Art Gallery
    [20, 30, 15, 22, 0]   # From Shopping Mall
]

# Constraints
BUDGET_CAP = 50
PLANNING_HORIZON = 14 * 60  # 14 hours (6 AM to 8 PM)

# Old itinerary data (for re-optimization)
# Indices correspond to: Museum, Park, Restaurant, Art Gallery, Shopping Mall
OLD_VISIT = [True, True, True, True, False]  # Shopping Mall was not visited before
OLD_START = [
    9 * 60,   # Museum started at 9:00 AM
    6 * 60,   # Park started at 6:00 AM
    11 * 60,  # Restaurant started at 11:00 AM
    10 * 60,  # Art Gallery started at 10:00 AM
    0         # Shopping Mall not visited (placeholder)
]

# Penalty weights for re-optimization
PENALTY_DROP_POI = 100        # High penalty for dropping a previously visited POI
PENALTY_TIME_SHIFT = 1        # Penalty per minute of time shift
REWARD_VISIT_POI = 50         # Reward for visiting a POI (balances penalties)

# Difficulty data (for user-first optimization)
# Indices correspond to: Museum, Park, Restaurant, Art Gallery, Shopping Mall
CROWD_LEVEL = [8, 3, 6, 5, 9]      # Crowd level 0-10 (10 = very crowded)
WEATHER_PENALTY = [2, 8, 1, 3, 2]  # Weather impact 0-10 (10 = severe weather impact)

# Difficulty sensitivity weights (configurable)
TRAVEL_FATIGUE_WEIGHT = 0.5        # Weight per minute of travel time
CROWD_SENSITIVITY = 5.0            # Multiplier for crowd discomfort
WEATHER_SENSITIVITY = 3.0          # Multiplier for weather discomfort

