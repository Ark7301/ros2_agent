# Human-Surrogate Memory Demo

## Purpose

Run the first-stage ARIA memory validation demo using a developer carrying a camera as the robot surrogate.

## Operator Workflow

1. Read the current movement instruction in the local operator console.
2. Execute the movement.
3. Upload `front`, `left`, `right`, and `back` images.
4. Click `Completed` or `Failed`.

## Demo Command

```bash
python scripts/run_human_surrogate_memory_demo.py
```

## Expected Success Signals

- MOSAIC prints ARIA context summaries
- checkpoint memory grows as exploration proceeds
- revisit tasks choose candidate checkpoints from memory
- at least one revisit succeeds using stored memory
