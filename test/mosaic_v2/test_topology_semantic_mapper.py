from mosaic.runtime.human_surrogate_models import SemanticObservation
from mosaic.runtime.topology_semantic_mapper import TopologySemanticMapper


def test_mapper_adds_root_checkpoint() -> None:
    mapper = TopologySemanticMapper()
    node = mapper.add_checkpoint(
        checkpoint_id="cp-01",
        parent_checkpoint_id=None,
        motion_from_parent=None,
        observation=SemanticObservation(
            checkpoint_id="cp-01",
            predicted_room="客厅",
            room_confidence=0.9,
            landmarks=["沙发"],
            objects=[],
            relations=[],
            evidence_summary="客厅里看到沙发",
        ),
    )
    assert node.checkpoint_id == "cp-01"
    assert node.resolved_room_label == "客厅"


def test_mapper_builds_target_index() -> None:
    mapper = TopologySemanticMapper()
    mapper.add_checkpoint(
        checkpoint_id="cp-01",
        parent_checkpoint_id=None,
        motion_from_parent=None,
        observation=SemanticObservation(
            checkpoint_id="cp-01",
            predicted_room="卧室",
            room_confidence=0.92,
            landmarks=["床"],
            objects=["黄色毛巾"],
            relations=[{"type": "near_landmark", "source": "黄色毛巾", "target": "床"}],
            evidence_summary="卧室里看到床和黄色毛巾",
        ),
    )
    index = mapper.build_target_index("黄色毛巾")
    assert index.target_label == "黄色毛巾"
    assert "卧室" in index.candidate_room_labels
    assert "cp-01" in index.candidate_checkpoint_ids
