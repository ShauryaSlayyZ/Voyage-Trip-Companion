# POI Optimizer - OR-Tools CP-SAT

A modular Python project for optimizing Point of Interest (POI) visits using Google OR-Tools CP-SAT solver.

## Project Structure

```
NextStep 2/
├── optimizer.py    # Main entry point
├── data.py        # POI dataset and travel time matrix
├── model.py       # CP-SAT model building logic
└── solver.py      # Solver execution and result formatting
```

## Installation

```bash
pip install ortools
```

## Usage

```bash
python optimizer.py
```

## Features

- **Interval-based scheduling** using CP-SAT's `NewOptionalIntervalVar`
- **Constraints:**
  - Mandatory POIs must be visited
  - Respect opening hours for each POI
  - Budget cap enforcement
  - No overlapping visits (NoOverlap constraint)
  - Travel time between consecutive POIs
- **Objective:** Maximize number of visited POIs

## Modular Design

- **`data.py`**: Configuration layer - easily modify POIs, travel times, and constraints
- **`model.py`**: Pure logic - build the CP-SAT model independently
- **`solver.py`**: Presentation layer - solve and format results
- **`optimizer.py`**: Orchestration - minimal entry point (23 lines)
