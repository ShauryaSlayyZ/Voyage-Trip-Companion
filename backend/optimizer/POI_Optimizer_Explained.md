# POI Optimizer - Complete Explanation (Plain English)

## What Does This Optimizer Do?

Imagine you're planning a day trip and want to visit several places (museums, parks, restaurants, etc.). But you have limited time, a budget, and each place has opening hours. Some places are far apart, and weather might affect outdoor locations. **This optimizer figures out the best schedule for you.**

---

## The Big Picture

### Input (What You Tell The Optimizer)
- **List of places** (POIs - Points of Interest) with:
  - How long you'll spend there
  - How much it costs
  - When they're open
  - Whether it's mandatory (must visit)
- **Travel time** between each pair of places
- **Your budget** (total money you can spend)
- **Planning horizon** (how many hours you have)
- **Optional:** Old schedule, weather conditions, crowd levels

### Output (What The Optimizer Gives You)
- **Which places to visit** and which to skip
- **Exact start time** for each visit
- **Total cost and time used**

---

## How Does It Work? A Step-by-Step Explanation

### 1. Creating Decision Variables

Think of these as **questions the optimizer needs to answer**:

#### For Each Place:
- **"Should we visit this place?"** (yes/no)
- **"When should we start visiting?"** (a specific time)
- **"When will we finish?"** (start time + duration)

**Interval Variables:** The clever part! Instead of manually tracking when each visit happens, we create an "interval" for each place - a time block that represents the visit. This interval is only "active" if we decide to visit that place.

**Example:**
- Museum visit = interval from 9:00 AM to 11:00 AM (2 hours)
- This interval only "exists" if we choose to visit the Museum

### 2. Adding Constraints (The Rules)

These are **hard rules** that must be followed, no exceptions:

#### Constraint 1: Mandatory Places Must Be Visited
```
If Museum is marked as "mandatory" → We MUST visit it
```

Simple as that. Some places are non-negotiable.

#### Constraint 2: Respect Opening Hours
```
If Park opens at 6:00 AM and closes at 8:00 PM →
The visit must START after 6:00 AM AND END before 8:00 PM
```

Can't visit a closed place!

#### Constraint 3: Budget Limit
```
Add up the cost of all visited places ≤ Budget
```

If you have $50 and visit Museum ($15) + Restaurant ($25) + Art Gallery ($10), that's exactly $50. ✓

#### Constraint 4: No Overlapping Visits
```
You can't be in two places at once!
```

This is where interval variables shine. The optimizer uses a special "NoOverlap" constraint that ensures all your visit intervals don't clash.

**Example:**
- Museum: 9:00-11:00 ✓
- Restaurant: 11:00-12:00 ✓ (immediately after)
- Park: 10:00-11:30 ✗ (overlaps with Museum!)

#### Constraint 5: Travel Time Between Places
```
If you visit Museum then Restaurant:
Restaurant start time ≥ Museum end time + Travel time from Museum to Restaurant
```

**Example:**
- Museum ends at 11:00
- Travel from Museum to Restaurant = 10 minutes
- Restaurant can start at 11:10 or later ✓

The optimizer ensures proper spacing between visits.

### 3. Defining the Objective (What Are We Optimizing For?)

This is the **goal** - what makes one schedule better than another.

#### Mode 1: Standard Optimization
```
MAXIMIZE: Number of places visited
```

Simple! Visit as many places as possible while respecting all constraints.

#### Mode 2: Re-optimization (When Plans Change)
```
MINIMIZE: Total Penalty
Where Penalty = 
  + (Penalty for dropping previously visited places) × 100
  + (Penalty for time shifts) × 1 per minute
  + (Crowd discomfort) × crowd_sensitivity × crowd_level
  + (Weather discomfort) × weather_sensitivity × weather_penalty
  + (Travel fatigue) × travel_weight × total_travel_time
  - (Reward for visiting places) × visit_reward
```

**In Plain English:**
When something disrupts your plan (weather, crowds, etc.), the optimizer tries to:
- **Keep your original schedule as much as possible** (high penalty for changes)
- **Drop places that are now problematic** (outdoor place in rain)
- **Shift visit times minimally** (small penalty per minute of change)
- **Balance between keeping the plan stable and avoiding discomfort**

---

## Understanding Penalties and Rewards

### Why Penalties?

Think of penalties as **costs** for undesirable outcomes:

**High Weather Penalty (e.g., Park in heavy rain):**
- Park's weather penalty = 15/10 (severe)
- Weather sensitivity = 8.0
- **Penalty if visiting Park = 15 × 8.0 = 120 points**

**Dropping a Previously Planned POI:**
- Penalty for dropping = 100 points
- If Park was in original plan but we drop it: **+100 penalty points**

**Time Shift:**
- Penalty per minute = 1
- If Museum shifts from 9:00 to 9:15: **+15 penalty points**

### Why Rewards?

Rewards are **negative penalties** (they reduce the total):

**Visiting a POI:**
- Reward per visit = 50 points
- Visit 4 places: **-200 penalty points** (good!)

### The Balance

The optimizer finds the schedule that **minimizes total penalty**:

**Example Scenario: Heavy Rain Expected**

**Option A: Keep Park in schedule**
```
Penalties:
  + Park weather penalty: 15 × 8.0 = +120
  - Visit 4 POIs: 4 × 50 = -200
  Total Penalty: -80
```

**Option B: Drop Park from schedule**
```
Penalties:
  + Dropped Park: +100
  - Visit 3 POIs: 3 × 50 = -150
  Total Penalty: -50
```

**Result:** Option A has lower penalty (-80 < -50), so **keep Park** unless the weather gets even worse!

---

## Special Features Explained

### 1. Interval Variables (The Magic Behind Scheduling)

**Old Way (Manual):**
- Track position of each visit (1st, 2nd, 3rd...)
- Manually ensure no overlaps
- Complex and error-prone

**New Way (Interval Variables):**
- Each visit is a "time block" (interval)
- Automatically handled by the solver
- Just say "these intervals can't overlap" - solver figures out the rest!

**Why It's Better:**
- Simpler code
- Faster solving
- More reliable

### 2. Precedence Constraints (Travel Time Logic)

Instead of saying "POI A must come before POI B," we use **precedence**:

```
If both POI A and POI B are visited:
  Either: A ends + travel(A→B) ≤ B starts
  Or: B ends + travel(B→A) ≤ A starts
```

The solver picks which order makes sense!

### 3. Linearization (Making Math Work)

Some things need special handling for the solver:

**Absolute Value:**
We want: penalty = |new_time - old_time|

But solvers need linear math, so we split it:
```
penalty = shift_positive + shift_negative
where: new_time - old_time = shift_positive - shift_negative
```

**Example:**
- Old time: 9:00 (540 minutes)
- New time: 9:15 (555 minutes)
- Difference: +15 minutes
- shift_positive = 15, shift_negative = 0
- Penalty = 15 + 0 = 15 ✓

---

## Real-World Example Walkthrough

### Scenario: Weekend Day Trip

**Original Plan (Generated by Standard Mode):**
1. 06:00 - Park (90 min, $0)
2. 09:00 - Museum (120 min, $15) 🔒 Mandatory
3. 11:00 - Restaurant (60 min, $25) 🔒 Mandatory
4. 12:00 - Art Gallery (75 min, $10)

**Total: 4 POIs, $50 cost**

### Disruption: Heavy Rain Alert! 🌧️

Weather forecast changes - heavy rain expected!

**Updated Weather Penalties:**
- Park: 8 → 18 (outdoor, severely affected!)
- Museum: 2 (indoor, still fine)
- Restaurant: 1 (indoor, still fine)
- Art Gallery: 3 (indoor, minimal impact)

### Re-optimization Process

The optimizer recalculates:

**Keeping Park:**
- Weather penalty: 18 × 8.0 = 144 points
- Visit reward: -50 points
- Net penalty from Park: +94 points

**Dropping Park:**
- Drop penalty: 100 points
- Lost visit reward: +50 points (fewer visits)
- Net penalty from dropping: +150 points

**WAIT!** But if we keep Park, we also get the weather penalty (+144), which when combined with the drop penalty analysis, makes dropping Park the better choice when weather sensitivity is high enough.

**Re-optimized Plan:**
1. 09:00 - Museum (120 min, $15) 🔒 Mandatory
2. 11:00 - Restaurant (60 min, $25) 🔒 Mandatory
3. 12:00 - Art Gallery (75 min, $10)

**Total: 3 POIs, $50 cost**

**Change:** ❌ DROPPED Park (reason: severe weather impact)

---

## Tuning the Optimizer (For Advanced Users)

### Making It Conservative (Resist Changes)
```python
PENALTY_DROP_POI = 200        # Very high penalty for dropping
PENALTY_TIME_SHIFT = 5        # High penalty for time changes
WEATHER_SENSITIVITY = 3.0     # Lower weather sensitivity
REWARD_VISIT_POI = 30         # Lower reward (quality over quantity)
```

Result: Keeps original plan unless absolutely necessary to change.

### Making It Adaptive (Accept Changes)
```python
PENALTY_DROP_POI = 50         # Lower penalty for dropping
PENALTY_TIME_SHIFT = 0.5      # Low penalty for time changes
WEATHER_SENSITIVITY = 10.0    # Very sensitive to weather
REWARD_VISIT_POI = 100        # High reward (quantity focused)
```

Result: Readily adapts to changing conditions.

### User-First Mode (Comfort Priority)
```python
CROWD_SENSITIVITY = 10.0      # Strongly avoid crowds
WEATHER_SENSITIVITY = 8.0     # Strongly avoid bad weather
TRAVEL_FATIGUE_WEIGHT = 2.0   # Minimize travel time
REWARD_VISIT_POI = 40         # Prefer fewer, better experiences
```

Result: Prioritizes user comfort over visiting many places.

---

## Common Questions

### Q: Why did it drop this POI?
**A:** Check these factors:
1. Was weather/crowd penalty too high?
2. Did it violate time/budget constraints?
3. Was dropping it lower total penalty than keeping it?

### Q: Why didn't it visit more places?
**A:** One of these constraints was hit:
1. Budget limit reached
2. Time limit reached (planning horizon)
3. Mandatory POIs + travel time filled the schedule
4. Difficulty penalties too high for remaining POIs

### Q: Can I force it to visit a specific POI?
**A:** Yes! Mark it as `mandatory: True` in the POI data.

### Q: Why are times sometimes odd (like 12:47)?
**A:** The optimizer works in minutes and finds the mathematically optimal time. You can round to nice times (like 1:00 PM) manually if preferred.

---

## Summary

This optimizer is a **smart scheduler** that:
1. ✅ Understands complex constraints (time, money, travel, mandatory visits)
2. ✅ Uses interval variables for elegant scheduling
3. ✅ Balances multiple objectives (visits vs. comfort vs. stability)
4. ✅ Adapts plans when disruptions occur
5. ✅ Finds mathematically optimal solutions in seconds

**The Magic:** It solves in seconds what would take humans hours of trial-and-error!

**The Power:** It can handle real-world complexity (weather, crowds, traffic, budget changes) and instantly re-optimize.

**The Flexibility:** Tunable weights let you prioritize what matters (more visits? comfortable experience? stable plans?).

---

**Created for:** Voyage Trip Companion Backend
**Technology:** Google OR-Tools CP-SAT Solver
**Date:** February 2026
