from mosaic.runtime.human_surrogate_models import MemoryTargetIndex
from mosaic.runtime.recall_revisit_orchestrator import RecallAndRevisitOrchestrator


def test_orchestrator_prefers_first_candidate_checkpoint() -> None:
    orchestrator = RecallAndRevisitOrchestrator()
    checkpoint_path = orchestrator.build_candidate_path(
        current_checkpoint_id="cp-01",
        edges={
            "cp-01": ["cp-02"],
            "cp-02": ["cp-01", "cp-03"],
            "cp-03": ["cp-02"],
        },
        target_index=MemoryTargetIndex(
            target_label="黄色毛巾",
            candidate_checkpoint_ids=["cp-03"],
            candidate_room_labels=["卧室"],
        ),
    )
    assert checkpoint_path == ["cp-01", "cp-02", "cp-03"]


def test_orchestrator_switches_to_next_candidate() -> None:
    orchestrator = RecallAndRevisitOrchestrator()
    next_candidate = orchestrator.next_candidate(
        ["cp-03", "cp-07"],
        exhausted={"cp-03"},
    )
    assert next_candidate == "cp-07"
