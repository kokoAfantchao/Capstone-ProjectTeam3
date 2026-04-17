"""
lucidchart_builder.py
Builds a LucidChart .lucid diagram from BigQuery nodes/edges views
and imports it into LucidChart via the API.

Required env vars:
  LUCID_ACCESS_TOKEN    — direct bearer token  (preferred)
  -- OR --
  LUCID_CLIENT_ID       
  LUCID_CLIENT_SECRET   
  LUCID_REFRESH_TOKEN   — OAuth2 refresh flow

BigQuery views (set via env vars or defaults):
  NODES_VIEW   vw_lucid_nodes_all
  EDGES_VIEW   vw_lucid_edges_all
"""

import hashlib
import io
import json
import math
import os
import re
import zipfile
from collections import defaultdict
from statistics import median

import requests
from bq_manager import BQ_PROJECT, BQ_DATASET, get_client

# ──────────────────────────────────────────────
# Config (read once at module level)
# ──────────────────────────────────────────────

NODES_VIEW = os.getenv("NODES_VIEW", "vw_lucid_nodes_all")
EDGES_VIEW = os.getenv("EDGES_VIEW", "vw_lucid_edges_all")

LUCID_CLIENT_ID     = os.getenv("LUCID_CLIENT_ID", "NEhXzDpgVSIhQKJSXzFyG0rJYshiuh5rfHfevyz1")
LUCID_CLIENT_SECRET = os.getenv("LUCID_CLIENT_SECRET", "_-RBdkkEmu-C0FRb6IXHltrnV3BPxUKq5HRQZg-pD63_1viQcw_8mVAc50ZdTHaRer_Gkr794qaKSte51oGg")
LUCID_REFRESH_TOKEN = os.getenv("LUCID_REFRESH_TOKEN", "")
LUCID_ACCESS_TOKEN  = os.getenv("LUCID_ACCESS_TOKEN", "")

LUCID_TOKEN_URL  = "https://api.lucid.co/oauth2/token"
LUCID_IMPORT_URL = "https://api.lucid.co/v1/documents"

BOX_W       = int(os.getenv("LUCID_BOX_W", "180"))
BOX_H       = int(os.getenv("LUCID_BOX_H", "60"))
ROW_GAP     = int(os.getenv("LUCID_ROW_GAP", "90"))
COL_GAP     = int(os.getenv("LUCID_COL_GAP", "220"))
TOP_Y       = int(os.getenv("LUCID_TOP_Y", "100"))
LEFT_X      = int(os.getenv("LUCID_LEFT_X", "100"))
MID_GAP     = int(os.getenv("LUCID_MID_GAP", "340"))
ROWS_PER_COL = int(os.getenv("LUCID_ROWS_PER_COL", "10"))

PAGE_RULES = [
    {"id": "user_ou",         "title": "Users to OUs",           "src": {"user"},             "dst": {"ou"}},
    {"id": "group_container", "title": "Groups to Containers",   "src": {"group"},            "dst": {"container", "ou"}},
    {"id": "computer_ou",     "title": "Computers to OUs",       "src": {"computer"},         "dst": {"ou"}},
    {"id": "lease_scope",     "title": "Leases to Scopes",       "src": {"lease"},            "dst": {"scope"}},
    {"id": "lease_dns",       "title": "Leases to DNS",          "src": {"lease"},            "dst": {"dns"}},
    {"id": "dns_computer",    "title": "DNS to Computers",       "src": {"dns"},              "dst": {"computer"}},
    {"id": "core_ad",         "title": "Core AD",                "src": {"domain", "forest", "site", "dc"}, "dst": {"domain", "forest", "site", "dc"}},
]

GROUP_COLOR_PALETTE = [
    {"fill": "#DCEBFF", "line": "#5B8FD9"},
    {"fill": "#DDF5E3", "line": "#4E9B63"},
    {"fill": "#FFF1CC", "line": "#C9971E"},
    {"fill": "#FCE4EC", "line": "#C05A7D"},
    {"fill": "#EFE3FF", "line": "#7A59B5"},
    {"fill": "#E8F7F7", "line": "#4E9DA0"},
    {"fill": "#FFE7CC", "line": "#C97A1E"},
]

# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def lucid_id(prefix, raw_value, max_len=36):
    digest = hashlib.sha1(str(raw_value).encode()).hexdigest()[:12]
    clean  = re.sub(r"[^A-Za-z0-9._~-]+", "", str(prefix))[:20]
    return f"{clean}-{digest}"[:max_len]


def node_prefix(node_id):
    return str(node_id).split("|", 1)[0].lower()


def short_label(text, max_len=28):
    text = str(text)
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def shape_for_prefix(prefix):
    mapping = {
        "user": "process", "group": "document", "ou": "terminator",
        "container": "terminator", "scope": "database", "lease": "data",
        "dns": "display", "computer": "process", "domain": "process",
        "forest": "process", "site": "note", "dc": "process",
    }
    return mapping.get(prefix, "process")


def colors_for_target(dst_id):
    idx = int(hashlib.sha1(str(dst_id).encode()).hexdigest(), 16) % len(GROUP_COLOR_PALETTE)
    return GROUP_COLOR_PALETTE[idx]


def sort_nodes(nodes):
    return sorted(nodes, key=lambda n: (str(n.get("node_label", "")).lower(), str(n.get("node_id", ""))))


def median_or_default(values, default_value=10_000):
    return float(median(values)) if values else float(default_value)


def reorder_bipartite(left_nodes, right_nodes, edges):
    left_by_id  = {str(n.get("node_id")): n for n in left_nodes}
    right_by_id = {str(n.get("node_id")): n for n in right_nodes}
    left_order  = sort_nodes(left_nodes)
    right_order = sort_nodes(right_nodes)
    left_nbrs   = defaultdict(list)
    right_nbrs  = defaultdict(list)

    for edge in edges:
        s, d = str(edge.get("src_node_id")), str(edge.get("dst_node_id"))
        if s in left_by_id and d in right_by_id:
            left_nbrs[s].append(d)
            right_nbrs[d].append(s)

    for _ in range(3):
        lpos = {str(n.get("node_id")): i for i, n in enumerate(left_order)}
        right_order = sorted(right_order, key=lambda n: (
            median_or_default([lpos[x] for x in right_nbrs[str(n.get("node_id"))] if x in lpos]),
            str(n.get("node_label", "")).lower(),
        ))
        rpos = {str(n.get("node_id")): i for i, n in enumerate(right_order)}
        left_order = sorted(left_order, key=lambda n: (
            median_or_default([rpos[x] for x in left_nbrs[str(n.get("node_id"))] if x in rpos]),
            str(n.get("node_label", "")).lower(),
        ))

    return left_order, right_order


def compute_box_position(index, base_x):
    subcol = index // ROWS_PER_COL
    row    = index % ROWS_PER_COL
    return base_x + (subcol * COL_GAP), TOP_Y + (row * ROW_GAP)


# ──────────────────────────────────────────────
# BigQuery fetchers
# ──────────────────────────────────────────────

def _run_query(sql):
    client = get_client()
    return [dict(row.items()) for row in client.query(sql).result()]


def fetch_nodes():
    return _run_query(f"SELECT * FROM `{BQ_PROJECT}.{BQ_DATASET}.{NODES_VIEW}`")


def fetch_edges():
    return _run_query(f"SELECT * FROM `{BQ_PROJECT}.{BQ_DATASET}.{EDGES_VIEW}`")


# ──────────────────────────────────────────────
# LucidChart Auth
# ──────────────────────────────────────────────

def get_access_token():
    # Read dynamically so tokens set at runtime (e.g. via OAuth callback) are picked up.
    access_token  = os.environ.get("LUCID_ACCESS_TOKEN")
    client_id     = os.environ.get("LUCID_CLIENT_ID", LUCID_CLIENT_ID)
    client_secret = os.environ.get("LUCID_CLIENT_SECRET", LUCID_CLIENT_SECRET)
    refresh_token = os.environ.get("LUCID_REFRESH_TOKEN", LUCID_REFRESH_TOKEN)

    if access_token:
        return access_token

    if not all([client_id, client_secret, refresh_token]):
        raise RuntimeError(
            "Missing Lucid credentials. Set LUCID_ACCESS_TOKEN or "
            "LUCID_CLIENT_ID + LUCID_CLIENT_SECRET + LUCID_REFRESH_TOKEN."
        )

    r = requests.post(LUCID_TOKEN_URL, json={
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
    }, timeout=60)

    if not r.ok:
        raise RuntimeError(f"Lucid token request failed {r.status_code}: {r.text}")

    new_token = r.json()["access_token"]
    # Cache it back so subsequent calls don't need to refresh again
    os.environ["LUCID_ACCESS_TOKEN"] = new_token
    return new_token


# ──────────────────────────────────────────────
# Diagram builders
# ──────────────────────────────────────────────

def relevant_edges_for_rule(edges, rule):
    return [
        e for e in edges
        if node_prefix(str(e.get("src_node_id"))) in rule["src"]
        and node_prefix(str(e.get("dst_node_id"))) in rule["dst"]
    ]


def build_rule_band(page_tag, rule, band_index, page_edges, node_by_id, top_y):
    if not page_edges:
        return [], []

    colors     = colors_for_target(rule["id"])
    left_x     = 120
    target_x   = 2500
    item_gap_y = 54
    box_w, box_h = 180, 42
    block_gap_y  = 110
    shapes, lines = [], []

    # Band title shape
    shapes.append({
        "id": lucid_id(f"band-{page_tag}-{band_index}", rule["title"]),
        "type": "note",
        "boundingBox": {"x": 60, "y": top_y + 10, "w": 420, "h": 36},
        "text": rule["title"],
        "opacity": 100,
    })

    edges_by_dst = {}
    for edge in page_edges:
        edges_by_dst.setdefault(str(edge.get("dst_node_id")), []).append(edge)

    current_y = top_y + 80

    for dst_id, dst_edges in sorted(
        edges_by_dst.items(),
        key=lambda x: str(node_by_id.get(x[0], {}).get("node_label", x[0])).lower()
    ):
        dst_node     = node_by_id.get(dst_id, {"node_label": dst_id})
        dst_shape_id = lucid_id(f"{page_tag}-{band_index}-T", dst_id)
        clr          = colors_for_target(dst_id)

        dst_edges = sorted(dst_edges, key=lambda e: str(
            node_by_id.get(str(e.get("src_node_id")), {}).get("node_label", "")
        ).lower())

        shapes.append({
            "id": dst_shape_id,
            "type": shape_for_prefix(node_prefix(dst_id)),
            "boundingBox": {"x": target_x, "y": current_y, "w": box_w, "h": box_h},
            "text": short_label(dst_node.get("node_label", dst_id)),
            "opacity": 100,
            "style": {"fill": {"type": "color", "color": clr["fill"]},
                      "stroke": {"color": clr["line"], "width": 1, "style": "solid"}},
        })

        for i, edge in enumerate(dst_edges):
            src_id      = str(edge.get("src_node_id"))
            src_node    = node_by_id.get(src_id, {"node_label": src_id})
            src_shape_id = lucid_id(f"{page_tag}-{band_index}-S", f"{dst_id}-{src_id}")
            src_y        = current_y + (i * item_gap_y)

            shapes.append({
                "id": src_shape_id,
                "type": shape_for_prefix(node_prefix(src_id)),
                "boundingBox": {"x": left_x, "y": src_y, "w": box_w, "h": box_h},
                "text": short_label(src_node.get("node_label", src_id)),
                "opacity": 100,
                "style": {"fill": {"type": "color", "color": clr["fill"]},
                          "stroke": {"color": clr["line"], "width": 1, "style": "solid"}},
            })

            lines.append({
                "id": lucid_id(f"ln-{page_tag}-{band_index}", f"{dst_id}-{src_id}-{i}"),
                "lineType": "elbow",
                "endpoint1": {"type": "shapeEndpoint", "style": "none",  "shapeId": src_shape_id, "position": {"x": 1, "y": 0.5}},
                "endpoint2": {"type": "shapeEndpoint", "style": "arrow", "shapeId": dst_shape_id, "position": {"x": 0, "y": 0.5}},
                "stroke": {"color": clr["line"], "width": 1, "style": "solid"},
            })

        current_y += max(box_h, len(dst_edges) * item_gap_y) + block_gap_y

    return shapes, lines


def build_composite_page(page_id, title, band_specs, node_by_id):
    shapes, lines = [], []
    current_top   = 30

    for band_index, spec in enumerate(band_specs, start=1):
        s, l = build_rule_band(page_id, spec["rule"], band_index, spec["edges"], node_by_id, current_top)
        shapes.extend(s)
        lines.extend(l)
        current_top += 1400

    return {
        "id": lucid_id("page", page_id),
        "title": title,
        "settings": {"fillColor": "#FFFFFF", "size": {"type": "custom", "w": 3600, "h": max(2200, current_top + 80)}},
        "shapes": shapes,
        "lines": lines,
    }


def build_document(nodes, edges):
    node_by_id = {str(n.get("node_id")): n for n in nodes}
    rule_by_id = {r["id"]: r for r in PAGE_RULES}
    pages      = []

    page_layouts = [
        {"id": "identity_page", "title": "Identity Relationships", "rule_ids": ["user_ou", "group_container", "core_ad"]},
        {"id": "systems_page",  "title": "Systems Relationships",  "rule_ids": ["dns_computer", "computer_ou"]},
        {"id": "network_page",  "title": "Network Relationships",  "rule_ids": ["lease_scope", "lease_dns"]},
    ]

    for layout in page_layouts:
        band_specs = [
            {"rule": rule_by_id[rid], "edges": relevant_edges_for_rule(edges, rule_by_id[rid])}
            for rid in layout["rule_ids"]
            if rid in rule_by_id and relevant_edges_for_rule(edges, rule_by_id[rid])
        ]
        if band_specs:
            pages.append(build_composite_page(layout["id"], layout["title"], band_specs, node_by_id))

    if not pages:
        pages.append({"id": lucid_id("page", "empty"), "title": "No Relationships Found",
                      "settings": {"fillColor": "#FFFFFF", "size": {"type": "custom", "w": 3600, "h": 1600}},
                      "shapes": [], "lines": []})

    return {"version": 1, "pages": pages}


def build_lucid_zip(document):
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("document.json", json.dumps(document, indent=2))
    mem.seek(0)
    return mem


def import_to_lucid(lucid_zip, access_token):
    r = requests.post(
        LUCID_IMPORT_URL,
        headers={"Authorization": f"Bearer {access_token}", "Lucid-Api-Version": "1"},
        files={"file": ("ad_relationships.lucid", lucid_zip.getvalue(), "x-application/vnd.lucid.standardImport")},
        data={"title": "AD Relationship Diagram", "product": "lucidchart"},
        timeout=120,
    )
    if not r.ok:
        raise RuntimeError(f"Lucid import failed {r.status_code}: {r.text}")
    return r.json()


# ──────────────────────────────────────────────
# Public entry point — called from main.py
# ──────────────────────────────────────────────

def trigger_lucid_import():
    """
    Fetch nodes/edges from BigQuery, build a .lucid diagram,
    and import it into LucidChart. Returns the API response dict.
    """
    nodes    = fetch_nodes()
    edges    = fetch_edges()
    document = build_document(nodes, edges)
    zip_file = build_lucid_zip(document)
    token    = get_access_token()
    result   = import_to_lucid(zip_file, token)

    return {
        "nodes_count": len(nodes),
        "edges_count": len(edges),
        "pages_count": len(document.get("pages", [])),
        "lucidchart_result": result,
    }
