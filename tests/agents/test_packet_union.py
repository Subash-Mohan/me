from pydantic import TypeAdapter

from app.agents.tools import ALL_TOOL_CLASSES, TOOL_CLASS_BY_NAME, Packet


def test_registry_contains_both_tools():
    names = {cls.NAME for cls in ALL_TOOL_CLASSES}
    assert names == {"search_memories", "manage_memory"}
    assert set(TOOL_CLASS_BY_NAME) == names


def test_packet_union_round_trips_text_delta():
    adapter = TypeAdapter(Packet)
    pkt = adapter.validate_python({"type": "text_delta", "delta": "hi"})
    assert pkt.delta == "hi"


def test_packet_union_round_trips_search_memories_start():
    adapter = TypeAdapter(Packet)
    pkt = adapter.validate_python({"type": "search_memories_start", "tool_call_id": "tc_1"})
    assert pkt.tool_call_id == "tc_1"


def test_packet_union_round_trips_manage_memory_end_error():
    adapter = TypeAdapter(Packet)
    pkt = adapter.validate_python(
        {
            "type": "manage_memory_end",
            "tool_call_id": "tc_2",
            "status": "error",
            "error": "MemoryNotFound",
        }
    )
    assert pkt.status == "error"
    assert pkt.error == "MemoryNotFound"
