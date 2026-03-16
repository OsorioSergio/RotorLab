# RotorLab Frontend (PyQt6)

## Run

From `python/`:

```powershell
pip install -r requirements.txt
rotorlab-app
```

## Current Scope

- Main app shell with three-row top section:
  - Global Project Controls
  - Environment tabs (fixed Orchestrate + dynamic tabs)
  - Context toolbar (changes with active environment)
- Middle workspace:
  - Orchestrate module library (drag source)
  - Orchestrate canvas (drop target)
- Bottom status bar:
  - state message
  - console dialog button

## Test

From `python/`:

```powershell
pytest
```
