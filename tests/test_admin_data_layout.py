"""Tier-1 tests for app.layout_pipeline_graph (pure geometry, no DB/network).

The pipeline graph is laid out left-to-right by longest-path column; v1 flows
``parsed_entries -> prepared_entries -> news_summary -> editorial ->
editorial_mp3`` (v0 keeps the older ``parsed_entries -> prepared_entries ->
editorial_mp3`` chain). Reads-
interests edges are rendered dashed. Tests only touch the returned geometry
and the static PIPELINE_GRAPHS definitions.
"""

from __future__ import annotations

from app import PIPELINE_GRAPHS, layout_pipeline_graph

VERSIONS = (0, 1)


def _node_geo(layout, key: str) -> dict:
    for node in layout["nodes"]:
        if node["key"] == key:
            return node
    raise AssertionError(f"missing node {key!r}")


def _definition_keys(version: int):
    """The node keys declared in PIPELINE_GRAPHS[version]["nodes"]."""
    nodes = PIPELINE_GRAPHS[version]["nodes"]
    if isinstance(nodes, dict):
        return set(nodes.keys())
    return {n["key"] for n in nodes}


def _edge_between(graph, frm: str, to: str) -> dict | None:
    for edge in graph["edges"]:
        if edge.get("from") == frm and edge.get("to") == to:
            return edge
    return None


def test_v1_has_news_summary_before_editorial():
    layout = layout_pipeline_graph(1)
    news_summary = _node_geo(layout, "news_summary")
    editorial = _node_geo(layout, "editorial")
    mp3 = _node_geo(layout, "editorial_mp3")
    assert news_summary["x"] < editorial["x"] < mp3["x"]


def test_v0_omits_editorial():
    layout = layout_pipeline_graph(0)
    assert all(node["key"] != "editorial" for node in layout["nodes"])
    _node_geo(layout, "editorial_mp3")
    assert _edge_between(PIPELINE_GRAPHS[0], "prepared_entries", "editorial_mp3")


def test_v0_omits_news_summary_v1_has_both():
    for node in layout_pipeline_graph(0)["nodes"]:
        assert node["key"] not in {"news_summary", "editorial"}
    layout_v1 = layout_pipeline_graph(1)
    _node_geo(layout_v1, "news_summary")
    _node_geo(layout_v1, "editorial")


def test_v1_news_summary_after_prepared_and_before_editorial():
    layout = layout_pipeline_graph(1)
    assert (
        _node_geo(layout, "prepared_entries")["x"]
        < _node_geo(layout, "news_summary")["x"]
    )
    assert _node_geo(layout, "news_summary")["x"] < _node_geo(layout, "editorial")["x"]
    assert _node_geo(layout, "editorial")["x"] < _node_geo(layout, "editorial_mp3")["x"]


def test_node_keys_match_graph():
    for version in VERSIONS:
        laid = layout_pipeline_graph(version)
        got_keys = {n["key"] for n in laid["nodes"]}
        assert got_keys == _definition_keys(version)


def test_geometry_sane():
    for version in VERSIONS:
        layout = layout_pipeline_graph(version)
        assert layout["width"] > 0 and layout["height"] > 0
        max_right = 0
        max_bottom = 0
        for node in layout["nodes"]:
            assert node["x"] >= 0 and node["y"] >= 0
            assert node["w"] > 0 and node["h"] > 0
            max_right = max(max_right, node["x"] + node["w"])
            max_bottom = max(max_bottom, node["y"] + node["h"])
        assert layout["width"] >= max_right
        assert layout["height"] >= max_bottom
        for edge in layout["edges"]:
            assert edge["d"].startswith("M ")
            assert " C " in edge["d"] or " L " in edge["d"]


def test_edges_connect_known_nodes():
    for version in VERSIONS:
        layout = layout_pipeline_graph(version)
        assert len(layout["edges"]) == len(PIPELINE_GRAPHS[version]["edges"])
        for edge in layout["edges"]:
            assert edge["d"]


def test_editorial_edge_chain_v1():
    assert _edge_between(PIPELINE_GRAPHS[1], "parsed_entries", "prepared_entries")
    assert _edge_between(PIPELINE_GRAPHS[1], "prepared_entries", "news_summary")
    assert _edge_between(PIPELINE_GRAPHS[1], "news_summary", "editorial")
    assert _edge_between(PIPELINE_GRAPHS[1], "editorial", "editorial_mp3")
    assert not _edge_between(PIPELINE_GRAPHS[1], "parsed_entries", "news_summary")
    assert not _edge_between(PIPELINE_GRAPHS[1], "prepared_entries", "editorial")
    for edge in PIPELINE_GRAPHS[0]["edges"]:
        assert (
            edge.get("from") not in {"news_summary", "editorial"}
            and edge.get("to") not in {"news_summary", "editorial"}
        )


def test_readers_edges_are_dashed_side_inputs():
    for version in VERSIONS:
        layout = layout_pipeline_graph(version)
        graph_edges = list(PIPELINE_GRAPHS[version]["edges"])
        reader_def_count = sum(1 for e in graph_edges if e.get("from") == "readers")
        dashed = [e for e in layout["edges"] if e["dashed"]]
        assert len(dashed) == reader_def_count
        for def_edge, laid_edge in zip(graph_edges, layout["edges"]):
            if def_edge.get("from") == "readers":
                assert laid_edge["dashed"] is True


def test_deterministic():
    first = [(n["x"], n["y"]) for n in layout_pipeline_graph(1)["nodes"]]
    second = [(n["x"], n["y"]) for n in layout_pipeline_graph(1)["nodes"]]
    assert first == second