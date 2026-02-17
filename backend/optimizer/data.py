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
