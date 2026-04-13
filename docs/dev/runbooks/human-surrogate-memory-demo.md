# Human-Surrogate Memory Demo

## Purpose

Run the first-stage ARIA memory validation demo using a developer carrying a camera as the robot surrogate.

## Operator Workflow

1. Read the current movement instruction in the local operator console.
2. Execute the movement.
3. Save `front`, `left`, `right`, and `back` images under
   `config/demo/observation_frames/...`.
4. Paste the saved file paths into the operator console for each view.
5. Click `Completed` or `Failed`.

## Demo Command

```bash
PYTHONPATH=. python3 scripts/run_human_surrogate_memory_demo.py
```

Stop the demo with `Ctrl+C`.

## Observation Frame Artifacts

Operator files should be stored under `config/demo/observation_frames` with one
subdirectory per step. The expected layout is:

- `config/demo/observation_frames/step-001/front.jpg`
- `config/demo/observation_frames/step-001/left.jpg`
- `config/demo/observation_frames/step-001/right.jpg`
- `config/demo/observation_frames/step-001/back.jpg`

Paste these file paths into the operator console for each required view.

## Expected Success Signals

- MOSAIC prints ARIA context summaries
- checkpoint memory grows as exploration proceeds
- revisit tasks choose candidate checkpoints from memory
- at least one revisit succeeds using stored memory
