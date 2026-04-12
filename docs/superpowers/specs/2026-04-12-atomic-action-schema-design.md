# Atomic Action Schema and Human Surrogate Models

## Context
- This is the foundational vocabulary for the human-surrogate ARIA memory validation demo. It defines the primitive operator actions and the shared data carriers that later operator-loop, VLM observation, and revisit orchestrator code will consume.
- Task 1 explicitly limits changes to the atomic action schema, shared human-surrogate data models, and the new test file. The implementation must be minimal and test-driven.

## Goals
1. Capture the set of atomic action names that the operator loop will emit, keeping the enum open to future actions but concrete enough for today.
2. Provide dataclass-first models (`ObservationFrameSet`, `SemanticObservation`, and longer-term records such as `CheckpointNode`/`MemoryTargetIndex`) to share data across runtime components without dragging in heavy dependencies.
3. Cover the new schema with a focused test that runs through serialization, enforcement of required imagery, and basic semantic observation fields.

## Approach options
1. **Minimal dataclasses per the spec (recommended).** Define `AtomicActionName` as a string `Enum`, implement `MotionCommand` with simple `to_dict`/`from_dict`, and create the shared data carriers as plain dataclasses. Advantage: no runtime dependencies, easy to import from anywhere, and the test is trivial to author and maintain. Drawback: no field validation beyond basic typing, but the tests focus on basic round-trip semantics so that is acceptable.
2. **Wrapper classes with validation logic.** We could write helper constructors or use `attrs`/`pydantic` to validate incoming payloads. This adds runtime complexity and conflicts with ``mosaic``'s current lightweight dataclass style. Implementation would take longer and add dependencies.
3. **Use typed dictionaries or NamedTuples.** This would reduce code volume but would make it harder to add behavior such as serialization helpers. Also, consumers already expect objects rather than raw mappings.

Recommendation: proceed with Option 1. It matches the user's spec, keeps imports light, and supports the TDD flow noted in the requirements.

## Implementation details
- `mosaic/runtime/atomic_action_schema.py` exports `AtomicActionName` and `MotionCommand`. `MotionCommand.to_dict` emits string values so JSON payloads can be shared with operator tooling; `from_dict` reconstructs the instance with default fallbacks.
- `mosaic/runtime/human_surrogate_models.py` exposes dataclasses for `ObservationFrameSet`, `SemanticObservation`, and higher-level memory tracking records. Each dataclass uses `field(default_factory=list)` when needed to avoid shared mutable state. No additional behavior is introduced beyond storing the data that downstream components will reference.
- `test/mosaic_v2/test_atomic_action_schema.py` exercises serialization round-trip, ensures `ObservationFrameSet` accepts four views, and that `SemanticObservation` can capture room info, objects, and relations.

## Testing plan
- Follow TDD: add the new test file first (done), run `pytest test/mosaic_v2/test_atomic_action_schema.py -q` to confirm failure due to missing modules (this confirms the tests gate the implementation), then implement the modules and rerun the same test (expected to pass).
- Rerun the same test after implementing the schema to confirm all defined assertions pass.

## Next steps
1. Keep this spec in repo history for future reference before proceeding to the next subtask (operator loop, VLM pipeline, etc.).
2. Once the spec is reviewed and approved, the next step would be to invoke the writing-plans skill and produce a plan for implementing the higher-level human-surrogate pipeline outputs.
