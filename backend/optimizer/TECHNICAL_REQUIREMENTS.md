# Technical Requirements Document
## POI Optimizer Module — Voyage Trip Companion Backend

**Version:** 1.1  
**Date:** February 2026  
**Status:** MVP  
**Location:** `backend/optimizer/`

---

## 0. Document Overview

| Field | Detail |
|-------|--------|
| **Product** | Voyage Trip Companion |
| **Module** | POI Optimizer |
| **Stage** | MVP (Minimum Viable Product) |
| **Author** | Vansh |
| **Last Updated** | February 2026 |

### Purpose
This document defines the technical requirements for the POI Optimizer module. It covers what the optimizer must do (functional requirements), how it must perform (non-functional requirements), the data it works with, and the constraints it enforces.

### Scope
This document covers **only the optimizer module** (`backend/optimizer/`). API endpoints, database schema, system architecture, and authentication are **out of scope for this version** and will be addressed in future documents.

### Intended Audience
Developers building or reviewing the optimizer module.

---

## 1. Overview

The POI Optimizer is a constraint-based scheduling engine integrated into the Voyage Trip Companion backend. It generates and re-optimizes day-trip itineraries using Google OR-Tools CP-SAT solver.

---

## 2. Functional Requirements

### FR-1: Standard Optimization
- **FR-1.1** The system SHALL select a subset of POIs to visit that maximizes the number of visited POIs.
- **FR-1.2** The system SHALL respect each POI's opening and closing hours.
- **FR-1.3** The system SHALL not exceed the total budget cap.
- **FR-1.4** The system SHALL schedule mandatory POIs in every solution.
- **FR-1.5** The system SHALL ensure no two visits overlap in time.
- **FR-1.6** The system SHALL enforce minimum travel time gaps between consecutive visits.

### FR-2: Re-optimization (Disruption Handling)
- **FR-2.1** The system SHALL accept a previous itinerary (`old_visit[]`, `old_start[]`) as input.
- **FR-2.2** The system SHALL penalize dropping any POI that was in the previous itinerary.
- **FR-2.3** The system SHALL penalize shifting a POI's start time from its previous value.
- **FR-2.4** The time-shift penalty SHALL be proportional to the absolute deviation in minutes.
- **FR-2.5** The system SHALL reward visiting POIs to balance against penalties.

### FR-3: Difficulty-Based Optimization
- **FR-3.1** The system SHALL accept per-POI crowd levels (0–10 scale).
- **FR-3.2** The system SHALL accept per-POI weather penalties (0–10 scale).
- **FR-3.3** The system SHALL penalize visiting POIs with high crowd or weather scores.
- **FR-3.4** The system SHALL penalize total travel time (travel fatigue).
- **FR-3.5** All difficulty penalties SHALL only apply when the POI is visited.

### FR-4: Unified Objective
- **FR-4.1** The objective SHALL be:  
  `Minimize( re-optimization penalties + difficulty penalties − visit rewards )`
- **FR-4.2** If no penalties or difficulty data are provided, the system SHALL fall back to maximizing visits.

### FR-5: Configurable Weights
- **FR-5.1** All penalty and sensitivity weights SHALL be defined as named constants in `data.py`.
- **FR-5.2** The following weights SHALL be configurable:
  - `PENALTY_DROP_POI` — cost for dropping a previously visited POI
  - `PENALTY_TIME_SHIFT` — cost per minute of time deviation
  - `REWARD_VISIT_POI` — reward per visited POI
  - `CROWD_SENSITIVITY` — multiplier for crowd discomfort
  - `WEATHER_SENSITIVITY` — multiplier for weather discomfort
  - `TRAVEL_FATIGUE_WEIGHT` — cost per minute of travel

### FR-6: Output
- **FR-6.1** The system SHALL output which POIs are visited and their start times.
- **FR-6.2** The system SHALL display total cost and number of POIs visited.
- **FR-6.3** In re-optimization mode, the system SHALL display a change log:
  - ❌ Dropped POIs
  - ✅ Newly added POIs
  - 🔄 Time-shifted POIs with direction and magnitude

---

## 3. Non-Functional Requirements

### NFR-1: Performance

> These numbers are confirmed for the **MVP stage**.

| Metric | Requirement |
|--------|-------------|
| Max POIs per request | **5** |
| Target solve time | **< 2 seconds** per request |
| Concurrent users | **20–30** (MVP scale) |
| Planning horizon | Configurable (default: 14 hours, 6:00 AM – 8:00 PM) |
| Budget cap | Configurable (default: $50) |

- **NFR-1.1** The solver SHALL return a solution in under 2 seconds for up to 5 POIs.
- **NFR-1.2** The system SHALL support 20–30 concurrent optimization requests at MVP scale.
- **NFR-1.3** The system SHALL not crash or hang if no feasible solution exists — it SHALL return a clear failure message.

### NFR-2: Modularity
- **NFR-2.1** The optimizer SHALL be structured as a Python package (`backend/optimizer/`).
- **NFR-2.2** Concerns SHALL be separated across files:
  - `data.py` — POI data, travel matrix, constants
  - `model.py` — CP-SAT model construction
  - `solver.py` — solving and result formatting
  - `optimizer.py` — entry point / orchestration

### NFR-3: Extensibility
- **NFR-3.1** The model SHALL accept all inputs as parameters (no hardcoded logic in `model.py`).
- **NFR-3.2** New disruption types SHALL be addable by modifying only `data.py` and `optimizer.py`.

### NFR-4: Testability
- **NFR-4.1** An automated test (`test_disruption.py`) SHALL verify re-optimization with a weather disruption.
- **NFR-4.2** An interactive test (`test_interactive.py`) SHALL allow manual testing of all disruption types.

### NFR-5: Security *(Future Priority)*
> Security and authentication are **not in scope for MVP**. The following are noted for future implementation.

- **NFR-5.1** *(Future)* API endpoints SHALL require authentication before accepting optimization requests.
- **NFR-5.2** *(Future)* Rate limiting SHALL be applied per user to prevent abuse.
- **NFR-5.3** *(Future)* All inputs SHALL be validated and sanitized before being passed to the solver.

---

## 4. Data Requirements

### DR-1: POI Schema
Each POI SHALL have the following fields:

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Display name |
| `duration` | int | Visit duration in minutes |
| `cost` | int | Entry cost in dollars |
| `opening_start` | int | Opening time in minutes from midnight |
| `opening_end` | int | Closing time in minutes from midnight |
| `mandatory` | bool | Whether visit is required |

### DR-2: Travel Time Matrix
- A 2D matrix where `TRAVEL_TIME[i][j]` is the travel time in minutes from POI `i` to POI `j`.
- Diagonal entries SHALL be 0.

### DR-3: Difficulty Arrays
- `CROWD_LEVEL[i]` — crowd level at POI `i` (0–10)
- `WEATHER_PENALTY[i]` — weather impact at POI `i` (0–10)
- Both arrays SHALL have the same length as the POI list.

### DR-4: Old Itinerary Arrays
- `OLD_VISIT[i]` — bool, whether POI `i` was in the previous plan
- `OLD_START[i]` — int, previous start time in minutes (0 if not visited)

---

## 5. Constraint Summary

| # | Constraint | Type | Enforced By |
|---|-----------|------|-------------|
| C1 | Mandatory POIs must be visited | Hard | `model.Add(visit[i] == 1)` |
| C2 | Visit within opening hours | Hard | `OnlyEnforceIf(visit[i])` |
| C3 | Total cost ≤ budget | Hard | `model.Add(total_cost <= budget)` |
| C4 | No overlapping visits | Hard | `model.AddNoOverlap(intervals)` |
| C5 | Travel time gap between visits | Hard | Precedence constraints |
| C6 | Drop penalty for old POIs | Soft | Penalty in objective |
| C7 | Time shift penalty | Soft | Linearized abs value in objective |
| C8 | Crowd discomfort | Soft | Penalty in objective |
| C9 | Weather discomfort | Soft | Penalty in objective |
| C10 | Travel fatigue | Soft | Penalty in objective |

---

## 6. Optimizer Modes

| Mode | `use_reoptimization` | `use_difficulty` | Objective |
|------|---------------------|------------------|-----------|
| Standard | False | False | Maximize visits |
| Re-optimize | True | False | Minimize deviation |
| Difficulty | False | True | Minimize difficulty |
| Full | True | True | Minimize deviation + difficulty |

---

## 7. Technology Stack

| Layer | Component | Technology / Version |
|-------|-----------|---------------------|
| **Solver** | Constraint optimizer | Google OR-Tools CP-SAT (`ortools`) |
| **Language** | Core implementation | Python 3.x |
| **Backend Framework** | API server | FastAPI |
| **Server** | ASGI server | Uvicorn |
| **Data Validation** | Request/response models | Pydantic |
| **Environment** | Config management | `python-dotenv` |
| **AI Integration** | LLM calls | OpenAI API |
| **Dependency Management** | Package list | `requirements.txt` |

### Key Dependencies (`requirements.txt`)
```
ortools          # CP-SAT solver
fastapi          # Web framework
uvicorn          # ASGI server
pydantic         # Data validation
python-dotenv    # Environment variables
openai           # AI/LLM integration
```

---

## 8. File Structure

```
backend/optimizer/
├── __init__.py                  # Package exports
├── data.py                      # POI data, travel matrix, constants
├── model.py                     # CP-SAT model builder
├── solver.py                    # Solver execution & output
├── optimizer.py                 # Entry point (orchestration)
├── test_disruption.py           # Automated disruption test
├── test_interactive.py          # Interactive test with user input
├── POI_Optimizer_Explained.md   # Plain-English explanation
├── TEST_README.md               # Test documentation
└── README.md                    # Module overview
```

---

## 9. Open Items / Future Work

| ID | Item | Priority |
|----|------|----------|
| OI-1 | Replace hardcoded POI data with dynamic API input | High |
| OI-2 | Expose optimizer via FastAPI endpoint | High |
| OI-3 | Add real-time crowd/weather data from external APIs | Medium |
| OI-4 | Support user-configurable sensitivity profiles | Medium |
| OI-5 | Add visual timeline comparison output | Low |
| OI-6 | Write unit tests for `model.py` and `solver.py` | Medium |
| OI-7 | Handle case where no feasible solution exists gracefully | High |

