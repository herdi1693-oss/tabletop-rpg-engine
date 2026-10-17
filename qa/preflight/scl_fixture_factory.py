import copy

from tools.visual.scene_continuity_guard import (
    canonical_digest,
    entity_state_digest,
    fact_value_digest,
    frame_state_digest,
)


def entity(epoch="REV-1"):
    return {
        "ENTITY_ID": "PC_AELIAN",
        "ENTITY_CLASS": "PC",
        "IDENTITY_AUTHORITY_ID": "VIS_PC_AELIAN_v1",
        "CAMPAIGN_VISUAL_ANCHOR_ID": None,
        "CURRENT_FORM": "BASE",
        "CURRENT_VISIBLE_EQUIPMENT": ["battleaxe"],
        "CURRENT_VISIBLE_WOUNDS_OR_MARKS": [],
        "CURRENT_VISIBLE_EFFECTS": [],
        "CURRENT_VISIBLE_TRANSFORMATION": None,
        "EVS_VALIDATION_RECEIPT_ID": f"EVS-AELIAN-{epoch}",
    }


def structure_fact(epoch="REV-1"):
    return {
        "FACT_ID": "STRUCTURE-WALL-NORTH",
        "FACT_CLASS": "IMMUTABLE_STRUCTURE",
        "VALUE": "STONE_WALL_PRESENT",
        "SOURCE_RECEIPT_ID": f"PSSP-STRUCT-{epoch}",
    }


def dynamic_fact(epoch="REV-1", value="UNLIT"):
    return {
        "FACT_ID": "SCENE-FIRE-1",
        "FACT_CLASS": "DYNAMIC_PLAYER_SAFE",
        "VALUE": value,
        "SOURCE_RECEIPT_ID": f"SCENE-STATE-{epoch}-{value}",
    }


def valid_group():
    return {
        "CONTINUITY_GROUP_ID": "CG-001",
        "OBSERVER_BRANCH_ID": "BRANCH-PARTY-A",
        "OPENING_STATE_EPOCH": "REV-1",
        "PLAYER_KNOWLEDGE_PROJECTION_ID": "PKP-REV-1-A",
        "PLAYER_KNOWLEDGE_PROJECTION_STATUS": "MATERIALIZED",
        "PLAYER_KNOWLEDGE_PROJECTION_OBSERVER_BRANCH_ID": "BRANCH-PARTY-A",
        "PLAYER_KNOWLEDGE_PROJECTION_SOURCE_STATE_EPOCH": "REV-1",
        "KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID": "KLG-REV-1-A",
        "KNOWLEDGE_LEAK_PREOUTPUT_GATE_STATUS": "PASS",
        "STATE_AUTHORITY": "DERIVED_NONAUTHORITATIVE",
        "CANON_DIRECTION": "CANON_TO_VISUAL_ONLY",
        "VISUAL_TO_CANON": False,
        "PROJECT_SOURCE_SLOT_DELTA": 0,
        "ENTITY_BASELINES": [entity("REV-1")],
        "SCENE_FACTS": [structure_fact("REV-1"), dynamic_fact("REV-1")],
    }


def valid_frame(index=0, previous=None, epoch="REV-1"):
    return {
        "FRAME_ID": f"FRAME-{index}",
        "CONTINUITY_GROUP_ID": "CG-001",
        "FRAME_INDEX": index,
        "PREVIOUS_FRAME_ID": previous,
        "OBSERVER_BRANCH_ID": "BRANCH-PARTY-A",
        "SOURCE_STATE_EPOCH": epoch,
        "PLAYER_KNOWLEDGE_PROJECTION_ID": f"PKP-{epoch}-A",
        "PLAYER_KNOWLEDGE_PROJECTION_STATUS": "MATERIALIZED",
        "PLAYER_KNOWLEDGE_PROJECTION_OBSERVER_BRANCH_ID": "BRANCH-PARTY-A",
        "PLAYER_KNOWLEDGE_PROJECTION_SOURCE_STATE_EPOCH": epoch,
        "KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID": f"KLG-{epoch}-A",
        "KNOWLEDGE_LEAK_PREOUTPUT_GATE_STATUS": "PASS",
        "TRACKED_ENTITIES": [entity(epoch)],
        "SCENE_FACTS": [structure_fact(epoch), dynamic_fact(epoch)],
        "IN_FRAME_ENTITY_IDS": ["PC_AELIAN"],
        "IN_FRAME_SCENE_FACT_IDS": ["STRUCTURE-WALL-NORTH", "SCENE-FIRE-1"],
        "CAMERA_SHOT_ID": "WIDE-1",
        "LIGHTING_STYLE_ID": "TORCH-MOODY",
        "COLOR_GRADE_ID": "DUNGEON-NEUTRAL",
        "VISUAL_MANIFEST_ID": f"VRM-FRAME-{index}-{epoch}",
        "PROJECT_SOURCE_SLOT_DELTA": 0,
    }


def empty_proofs():
    return {
        "PKP_RECEIPTS": {},
        "LEAK_GATE_RECEIPTS": {},
        "EVS_RECEIPTS": {},
        "PLAYER_SAFE_SOURCE_RECEIPTS": {},
        "APPLIED_EVENT_LEDGER_RECEIPTS": {},
        "VIL_RECEIPTS": {},
        "ENTITY_RENDER_RECEIPTS": {},
        "FACT_RENDER_RECEIPTS": {},
        "PLAYER_SAFE_RENDER_RECEIPTS": {},
    }


def add_player_safe_proofs(proofs, record, epoch_field):
    epoch = record[epoch_field]
    branch = record["OBSERVER_BRANCH_ID"]
    pkp_id = record["PLAYER_KNOWLEDGE_PROJECTION_ID"]
    leak_id = record["KNOWLEDGE_LEAK_PREOUTPUT_GATE_RECEIPT_ID"]
    proofs["PKP_RECEIPTS"][pkp_id] = {
        "RECEIPT_ID": pkp_id,
        "STATUS": "MATERIALIZED",
        "PLAYER_KNOWLEDGE_PROJECTION_ID": pkp_id,
        "OBSERVER_BRANCH_ID": branch,
        "SOURCE_STATE_EPOCH": epoch,
        "PROJECTION_DIGEST": canonical_digest({"PKP": pkp_id, "BRANCH": branch, "EPOCH": epoch}),
    }
    proofs["LEAK_GATE_RECEIPTS"][leak_id] = {
        "RECEIPT_ID": leak_id,
        "STATUS": "PASS",
        "PLAYER_KNOWLEDGE_PROJECTION_ID": pkp_id,
        "OBSERVER_BRANCH_ID": branch,
        "SOURCE_STATE_EPOCH": epoch,
    }


def add_entity_fact_proofs(proofs, record, entities_field, epoch_field):
    epoch = record[epoch_field]
    pkp = record["PLAYER_KNOWLEDGE_PROJECTION_ID"]
    branch = record["OBSERVER_BRANCH_ID"]
    for e in record[entities_field]:
        rid = e["EVS_VALIDATION_RECEIPT_ID"]
        proofs["EVS_RECEIPTS"][rid] = {
            "RECEIPT_ID": rid,
            "STATUS": "PASS",
            "ENTITY_ID": e["ENTITY_ID"],
            "ENTITY_CLASS": e["ENTITY_CLASS"],
            "IDENTITY_AUTHORITY_ID": e["IDENTITY_AUTHORITY_ID"],
            "PLAYER_KNOWLEDGE_PROJECTION_ID": pkp,
            "OBSERVER_BRANCH_ID": branch,
            "SOURCE_STATE_EPOCH": epoch,
            "ENTITY_STATE_DIGEST": entity_state_digest(e),
        }
    for fact in record["SCENE_FACTS"]:
        rid = fact["SOURCE_RECEIPT_ID"]
        source = {
            "RECEIPT_ID": rid,
            "STATUS": "PASS",
            "FACT_ID": fact["FACT_ID"],
            "FACT_CLASS": fact["FACT_CLASS"],
            "VALUE_DIGEST": fact_value_digest(fact),
            "PLAYER_KNOWLEDGE_PROJECTION_ID": pkp,
            "OBSERVER_BRANCH_ID": branch,
            "SOURCE_STATE_EPOCH": epoch,
        }
        if fact["FACT_CLASS"] == "IMMUTABLE_STRUCTURE":
            source.update({
                "SOURCE_KIND": "PLAYER_SAFE_STRUCTURE_PACKAGE",
                "PLAYER_SAFE_STRUCTURE_PACKAGE_ID": f"PSSP-{epoch}",
                "GEOMETRY_LOCK_ID": f"GL-{epoch}",
                "GEOMETRY_LOCK_STATUS": "PASS",
            })
        else:
            source["SOURCE_KIND"] = "PLAYER_KNOWLEDGE_PROJECTION"
        proofs["PLAYER_SAFE_SOURCE_RECEIPTS"][rid] = source


def valid_proofs(*frames):
    proofs = empty_proofs()
    group = valid_group()
    add_player_safe_proofs(proofs, group, "OPENING_STATE_EPOCH")
    add_entity_fact_proofs(proofs, group, "ENTITY_BASELINES", "OPENING_STATE_EPOCH")
    for frame in frames:
        add_player_safe_proofs(proofs, frame, "SOURCE_STATE_EPOCH")
        add_entity_fact_proofs(proofs, frame, "TRACKED_ENTITIES", "SOURCE_STATE_EPOCH")
    return proofs


def camera_transition(f0, f1, *fields):
    return {
        "CONTINUITY_GROUP_ID": "CG-001",
        "FROM_FRAME_ID": f0["FRAME_ID"],
        "TO_FRAME_ID": f1["FRAME_ID"],
        "CAUSES": [{
            "CAUSE_TYPE": "CAMERA_ONLY",
            "AFFECTED_KEYS": [f"PRESENTATION:{field}" for field in fields],
        }],
    }


def gameplay_transition(f0, f1, key, proofs, event_id="EVENT-77"):
    rid = f"AEL-{event_id}-{f0['SOURCE_STATE_EPOCH']}-{f1['SOURCE_STATE_EPOCH']}"
    if key.startswith("ENTITY:"):
        _, entity_id, field = key.split(":", 2)
        p = next(x for x in f0["TRACKED_ENTITIES"] if x["ENTITY_ID"] == entity_id)
        c = next(x for x in f1["TRACKED_ENTITIES"] if x["ENTITY_ID"] == entity_id)
        before, after = p.get(field), c.get(field)
    else:
        _, fact_id, _ = key.split(":", 2)
        p = next(x for x in f0["SCENE_FACTS"] if x["FACT_ID"] == fact_id)
        c = next(x for x in f1["SCENE_FACTS"] if x["FACT_ID"] == fact_id)
        before, after = p.get("VALUE"), c.get("VALUE")
    changeset = {key: {"BEFORE": before, "AFTER": after}}
    payload = {
        "EVENT_ID": event_id,
        "FROM_STATE_EPOCH": f0["SOURCE_STATE_EPOCH"],
        "TO_STATE_EPOCH": f1["SOURCE_STATE_EPOCH"],
        "AFFECTED_KEYS": [key],
        "AUTHORITATIVE_CHANGESET": changeset,
    }
    proofs["APPLIED_EVENT_LEDGER_RECEIPTS"][rid] = {
        "RECEIPT_ID": rid,
        "AUTHORITY": "APPLIED_EVENT_LEDGER",
        "STATUS": "PASS",
        "COMMIT_STATUS": "COMMITTED",
        "EVENT_ID": event_id,
        "TRANSACTION_RECEIPT_ID": f"TXR-{event_id}",
        "LOGICAL_COMMIT_INDEX": 77,
        "APPLIED_EVENT_LEDGER_CONTAINS_EVENT": True,
        "FROM_STATE_EPOCH": f0["SOURCE_STATE_EPOCH"],
        "TO_STATE_EPOCH": f1["SOURCE_STATE_EPOCH"],
        "COMMITTED_REVISION": f1["SOURCE_STATE_EPOCH"],
        "AFFECTED_KEYS": [key],
        "AUTHORITATIVE_CHANGESET": changeset,
        "AUTHORITATIVE_CHANGESET_DIGEST": canonical_digest(payload),
    }
    return {
        "CONTINUITY_GROUP_ID": "CG-001",
        "FROM_FRAME_ID": f0["FRAME_ID"],
        "TO_FRAME_ID": f1["FRAME_ID"],
        "CAUSES": [{
            "CAUSE_TYPE": "COMMITTED_GAMEPLAY_EVENT",
            "EVENT_ID": event_id,
            "APPLIED_EVENT_LEDGER_RECEIPT_ID": rid,
            "FROM_STATE_EPOCH": f0["SOURCE_STATE_EPOCH"],
            "TO_STATE_EPOCH": f1["SOURCE_STATE_EPOCH"],
            "AFFECTED_KEYS": [key],
        }],
    }, rid


def add_post_render_proofs(proofs, frame, render_id=None, render_hash=None):
    render_id = render_id or f"RENDER-{frame['FRAME_ID']}"
    render_hash = render_hash or canonical_digest({"RENDER_ARTIFACT_ID": render_id})
    common = {
        "FRAME_ID": frame["FRAME_ID"],
        "CONTINUITY_GROUP_ID": frame["CONTINUITY_GROUP_ID"],
        "RENDER_ARTIFACT_ID": render_id,
        "RENDER_ARTIFACT_HASH": render_hash,
        "VISUAL_MANIFEST_ID": frame["VISUAL_MANIFEST_ID"],
        "FRAME_STATE_DIGEST": frame_state_digest(frame),
    }
    vil_id = f"VIL-{frame['FRAME_ID']}-{render_id}"
    ps_id = f"PSR-{frame['FRAME_ID']}-{render_id}"
    proofs["VIL_RECEIPTS"][vil_id] = {"RECEIPT_ID": vil_id, "STATUS": "PASS", **common}
    proofs["PLAYER_SAFE_RENDER_RECEIPTS"][ps_id] = {"RECEIPT_ID": ps_id, "STATUS": "PASS", **common}
    entities = {x["ENTITY_ID"]: x for x in frame["TRACKED_ENTITIES"]}
    facts = {x["FACT_ID"]: x for x in frame["SCENE_FACTS"]}
    entity_refs = {}
    fact_refs = {}
    for entity_id in frame["IN_FRAME_ENTITY_IDS"]:
        rid = f"ECR-{frame['FRAME_ID']}-{entity_id}-{render_id}"
        entity_refs[entity_id] = rid
        proofs["ENTITY_RENDER_RECEIPTS"][rid] = {
            "RECEIPT_ID": rid, "STATUS": "PASS", "ENTITY_ID": entity_id,
            "ENTITY_STATE_DIGEST": entity_state_digest(entities[entity_id]), **common,
        }
    for fact_id in frame["IN_FRAME_SCENE_FACT_IDS"]:
        rid = f"FCR-{frame['FRAME_ID']}-{fact_id}-{render_id}"
        fact_refs[fact_id] = rid
        proofs["FACT_RENDER_RECEIPTS"][rid] = {
            "RECEIPT_ID": rid, "STATUS": "PASS", "FACT_ID": fact_id,
            "FACT_VALUE_DIGEST": fact_value_digest(facts[fact_id]), **common,
        }
    return {
        **common,
        "VISUAL_IDENTITY_LOCK_RECEIPT_ID": vil_id,
        "ENTITY_CONTINUITY_RECEIPT_IDS": entity_refs,
        "SCENE_FACT_CONTINUITY_RECEIPT_IDS": fact_refs,
        "PLAYER_SAFE_CONTENT_RECEIPT_ID": ps_id,
    }
