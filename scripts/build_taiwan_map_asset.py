from __future__ import annotations

import json
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://taiwan.md/assets/geo/taiwan-country.topo.json"
OUT = ROOT / "taiwan-map.js"


def load_topology() -> dict:
    req = Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=45) as response:
        return json.loads(response.read().decode("utf-8"))


def decode_arcs(topology: dict) -> list[list[tuple[float, float]]]:
    scale_x, scale_y = topology["transform"]["scale"]
    translate_x, translate_y = topology["transform"]["translate"]
    decoded = []
    for arc in topology["arcs"]:
        x = 0
        y = 0
        points = []
        for dx, dy in arc:
            x += dx
            y += dy
            points.append((x * scale_x + translate_x, y * scale_y + translate_y))
        decoded.append(points)
    return decoded


def arc_points(decoded: list[list[tuple[float, float]]], ref: int) -> list[tuple[float, float]]:
    if ref >= 0:
        return decoded[ref]
    return list(reversed(decoded[~ref]))


def ring_points(decoded: list[list[tuple[float, float]]], refs: list[int]) -> list[tuple[float, float]]:
    ring = []
    for ref in refs:
        pts = arc_points(decoded, ref)
        if ring:
            ring.extend(pts[1:])
        else:
            ring.extend(pts)
    return ring


def geometry_rings(decoded: list[list[tuple[float, float]]], geometry: dict) -> list[list[tuple[float, float]]]:
    if geometry["type"] == "Polygon":
        return [ring_points(decoded, refs) for refs in geometry["arcs"]]
    if geometry["type"] == "MultiPolygon":
        rings = []
        for polygon in geometry["arcs"]:
            rings.extend(ring_points(decoded, refs) for refs in polygon)
        return rings
    return []


def main() -> None:
    topology = load_topology()
    decoded = decode_arcs(topology)
    geometries = topology["objects"]["map"]["geometries"]
    all_points = []
    raw_shapes = []
    for geometry in geometries:
        rings = geometry_rings(decoded, geometry)
        raw_shapes.append((geometry["properties"], rings))
        for ring in rings:
            all_points.extend(ring)

    min_x = min(point[0] for point in all_points)
    max_x = max(point[0] for point in all_points)
    min_y = min(point[1] for point in all_points)
    max_y = max(point[1] for point in all_points)
    pad = 4
    width = 100 - pad * 2
    height = 120 - pad * 2
    scale = min(width / (max_x - min_x), height / (max_y - min_y))
    offset_x = (100 - (max_x - min_x) * scale) / 2
    offset_y = (120 - (max_y - min_y) * scale) / 2

    def project(point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        return (offset_x + (x - min_x) * scale, 120 - (offset_y + (y - min_y) * scale))

    shapes = []
    for props, rings in raw_shapes:
        projected_rings = []
        d_parts = []
        for ring in rings:
            projected = [project(point) for point in ring]
            projected_rings.append(projected)
            if not projected:
                continue
            commands = [f"M {projected[0][0]:.3f} {projected[0][1]:.3f}"]
            commands.extend(f"L {x:.3f} {y:.3f}" for x, y in projected[1:])
            commands.append("Z")
            d_parts.append(" ".join(commands))
        outer = max(projected_rings, key=len) if projected_rings else []
        label_x = sum(point[0] for point in outer) / len(outer) if outer else 0
        label_y = sum(point[1] for point in outer) / len(outer) if outer else 0
        shapes.append(
            {
                "name": props["name"],
                "id": props["id"],
                "d": " ".join(d_parts),
                "labelX": round(label_x, 2),
                "labelY": round(label_y, 2),
            }
        )

    payload = {
        "source": SOURCE_URL,
        "viewBox": "0 0 100 120",
        "shapes": shapes,
    }
    OUT.write_text("window.TAIWAN_MAP = " + json.dumps(payload, ensure_ascii=True) + ";\n", encoding="ascii")
    print(f"Wrote {len(shapes)} county paths to {OUT}")


if __name__ == "__main__":
    main()
