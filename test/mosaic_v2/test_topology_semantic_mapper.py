import pytest

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
    assert node.depth_from_start == 0


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
    assert index.supporting_landmarks == ["床"]
    assert index.confidence == 1.0


def test_mapper_add_checkpoint_missing_parent_raises() -> None:
    mapper = TopologySemanticMapper()
    observation = SemanticObservation(
        checkpoint_id="cp-02",
        predicted_room="厨房",
        room_confidence=0.85,
        landmarks=["餐桌"],
        objects=["红色杯子"],
        relations=[],
        evidence_summary="看到了红色杯子",
    )
    with pytest.raises(ValueError, match="parent checkpoint"):
        mapper.add_checkpoint(
            checkpoint_id="cp-02",
            parent_checkpoint_id="cp-01",
            motion_from_parent=None,
            observation=observation,
        )


def test_mapper_add_checkpoint_mismatched_checkpoint_id_raises() -> None:
    mapper = TopologySemanticMapper()
    observation = SemanticObservation(
        checkpoint_id="cp-04",
        predicted_room="书房",
        room_confidence=0.78,
        landmarks=["书桌"],
        objects=["笔记本"],
        relations=[],
        evidence_summary="书桌上有笔记本",
    )
    with pytest.raises(ValueError, match="observation checkpoint"):
        mapper.add_checkpoint(
            checkpoint_id="cp-03",
            parent_checkpoint_id=None,
            motion_from_parent=None,
            observation=observation,
        )


def test_mapper_build_target_index_missing_target_returns_zero_confidence() -> None:
    mapper = TopologySemanticMapper()
    mapper.add_checkpoint(
        checkpoint_id="cp-05",
        parent_checkpoint_id=None,
        motion_from_parent=None,
        observation=SemanticObservation(
            checkpoint_id="cp-05",
            predicted_room="客厅",
            room_confidence=0.9,
            landmarks=["茶几"],
            objects=["绿色枕头"],
            relations=[],
            evidence_summary="客厅里有绿色枕头",
        ),
    )
    index = mapper.build_target_index("不存在的目标")
    assert index.target_label == "不存在的目标"
    assert index.candidate_room_labels == []
    assert index.candidate_checkpoint_ids == []
    assert index.supporting_landmarks == []
    assert index.confidence == 0.0


def test_mapper_build_target_index_dedups_rooms_and_landmarks() -> None:
    mapper = TopologySemanticMapper()
    for checkpoint_id in ("cp-06", "cp-07"):
        mapper.add_checkpoint(
            checkpoint_id=checkpoint_id,
            parent_checkpoint_id=None,
            motion_from_parent=None,
            observation=SemanticObservation(
                checkpoint_id=checkpoint_id,
                predicted_room="厨房",
                room_confidence=0.8,
                landmarks=["冰箱", "橱柜"],
                objects=["蓝色杯子"],
                relations=[],
                evidence_summary="厨房里有蓝色杯子",
            ),
        )
    index = mapper.build_target_index("蓝色杯子")
    assert index.candidate_room_labels == ["厨房"]
    assert index.candidate_checkpoint_ids == ["cp-06", "cp-07"]
    assert sorted(index.supporting_landmarks) == ["冰箱", "橱柜"]
    assert index.confidence == 1.0
