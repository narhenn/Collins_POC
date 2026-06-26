"""Graph utilities for workflow execution.

Operates on React Flow format definitions:
  definition = {
      "nodes": [ { "id": "1", "type": "trigger", "data": {...}, ... }, ... ],
      "edges": [ { "source": "1", "target": "2", "label": "true", ... }, ... ],
  }
"""

from collections import defaultdict, deque


def parse_workflow(definition: dict) -> tuple[list[dict], list[dict]]:
    """Extract nodes and edges from a React Flow workflow definition."""
    nodes = definition.get("nodes", [])
    edges = definition.get("edges", [])
    return nodes, edges


def topological_sort(nodes: list[dict], edges: list[dict]) -> list[dict]:
    """Return *nodes* in topological (execution) order.

    Falls back to the original order if the graph contains cycles (should not
    happen for a valid workflow, but we degrade gracefully).
    """
    node_map = {n["id"]: n for n in nodes}
    in_degree: dict[str, int] = defaultdict(int)
    adj: dict[str, list[str]] = defaultdict(list)

    for n in nodes:
        in_degree.setdefault(n["id"], 0)

    for e in edges:
        src = e["source"]
        tgt = e["target"]
        adj[src].append(tgt)
        in_degree[tgt] += 1

    queue: deque[str] = deque()
    for nid, deg in in_degree.items():
        if deg == 0:
            queue.append(nid)

    sorted_ids: list[str] = []
    while queue:
        nid = queue.popleft()
        sorted_ids.append(nid)
        for neighbor in adj[nid]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # If not all nodes were visited there is a cycle; append remaining.
    if len(sorted_ids) < len(nodes):
        visited = set(sorted_ids)
        for n in nodes:
            if n["id"] not in visited:
                sorted_ids.append(n["id"])

    return [node_map[nid] for nid in sorted_ids if nid in node_map]


def get_next_nodes(
    node_id: str,
    edges: list[dict],
    branch: str | None = None,
) -> list[str]:
    """Return the IDs of nodes reachable from *node_id* via outgoing edges.

    If *branch* is supplied (e.g. ``"true"`` or ``"false"``), only edges whose
    ``label``, ``sourceHandle``, or ``data.label`` matches *branch* are
    followed.  If *branch* is ``None`` all outgoing edges are followed.
    """
    result: list[str] = []
    for e in edges:
        if e["source"] != node_id:
            continue

        if branch is not None:
            edge_label = (
                e.get("label")
                or e.get("sourceHandle")
                or (e.get("data") or {}).get("label")
                or ""
            )
            if edge_label.lower() != branch.lower():
                continue

        result.append(e["target"])
    return result
