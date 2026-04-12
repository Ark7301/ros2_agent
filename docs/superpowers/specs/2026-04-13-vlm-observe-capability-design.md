# VLM Observe Capability Design

- title: VLM Observe Capability Design
- status: active
- owner: repository-maintainers
- updated: 2026-04-13
- tags: vlm, capability, spec, mosaic, human-surrogate

## 1. Background

Task 3 of the human-surrogate ARIA memory validation project is the first concrete bridge between four-view checkpoint images and the semantic evidence ARIA stores. The previous pipeline only observed the `front` view, which violates the approved spec that requires all checkpoint views to be interpreted. This capability exists inside the `plugins/capabilities` surface and will be consumed by the higher-level ARIA orchestration stack.

## 2. Objective

- Build `VLMObserveCapability` (id: `vlm-observe`, kind: `capability`) that supports the `observe_scene` intent/tool.
- Aggregate Minimax VLM analyzer outputs over all provided checkpoint views (`front`, `left`, `right`, `back`) and expose them as a single semantic observation.
- Keep the initial release minimal: landmarks and relations are empty lists, but room/object aggregations plus the evidence summary must follow the approved rules.

## 3. Aggregation Requirements

1. Only analyze views actually provided in the `images` param; skip missing keys.
2. For each view, construct `CameraFrame(image_data=<bytes>, timestamp=time.time())` and call the injected analyzer via `analyze_frame(frame, scene_context="")`.
3. Predicted room: choose the `room_type` with the highest confidence across all views. Keep the confidence that produced it.
4. Objects: accumulate the union of `DetectedObject.label` values in the order they first appear (deduplicate while preserving insertion order).
5. Landmarks and relations: return `[]` for both to keep this slice minimal.
6. Evidence summary: mention the checkpoint id and the count of analyzed views (e.g., “Checkpoint cp-01 analyzed 3 views.”).

## 4. Data Flow

1. `execute("observe_scene", params, ctx)` validates `checkpoint_id` and `images`.
2. Walk `images` in deterministic order (`front`, `left`, `right`, `back`). When a view exists:
   - Build `CameraFrame`.
   - Await `analyzer.analyze_frame(frame, scene_context="")`.
   - Record the returned `DetectionResult`.
3. After all views finish, compute:
   - The best `RoomClassification` (drop views that returned `None`).
   - The ordered object label list.
   - Empty `landmarks`/`relations`.
   - An `evidence_summary` string describing how many views were analyzed for the checkpoint.
4. Return `ExecutionResult(success=True, data={...})` with the required fields.
5. `cancel` and `health_check` are minimal wrappers for cancellation and analyzer health; `create_plugin(analyzer=None)` bootstraps the capability for production or tests.

## 5. Testing Plan

1. The new `test/mosaic_v2/test_vlm_observe_capability.py` ensures:
   - Each of the four views is passed to the analyzer in `front`, `left`, `right`, `back` order.
   - Aggregated room classification picks the highest-confidence “卧室”.
   - Object union contains both “黄色毛巾” and “床”.
   - The plugin responds with the proper checkpoint id.
2. Tests drive TDD: the file is created first, `pytest` run to fail, then implementation added, and `pytest test/mosaic_v2/test_vlm_observe_capability.py test/mosaic_v2/test_vlm_pipeline.py -q` used to verify.
3. The existing `test/mosaic_v2/test_vlm_pipeline.py` guard ensures the analyzer contracts still hold.

## 6. Implementation Notes

- Use `PluginMeta` to describe the capability.
- `get_tool_definitions()` returns a single `observe_scene` tool with `checkpoint_id` and `images` (object with optional view keys) parameters.
- Analyzer calls remain sequential for simplicity; asynchronous concurrency has no ROI yet.
- Deduplication of objects uses a seen set to preserve labelling order.
- Evidence summary string looks like `f\"Checkpoint {checkpoint_id} analyzed {len(analyzed_views)} views.\"`.

## 7. Open Questions

- Should the evidence summary count the number of views that actually ran through the analyzer even when fewer than four are provided? (Assuming yes for now; otherwise we would still mention “analyzed {len(analyzed_views)} views”.)
