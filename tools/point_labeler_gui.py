#!/usr/bin/env python3
"""Tkinter GUI for labeling FunKPoint corresponding keypoints."""

from __future__ import annotations

import argparse
import colorsys
import csv
import re
import sys
from pathlib import Path
from typing import Callable, Literal

try:
    import tkinter as tk
    from tkinter import messagebox, ttk
except ImportError:  # pragma: no cover - exercised only on systems without Tk.
    tk = None
    messagebox = None
    ttk = None

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:  # pragma: no cover - exercised only on systems without Pillow.
    Image = None
    ImageDraw = None
    ImageTk = None


Role = Literal["reference", "test"]

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
DEFAULT_POINT_COUNT = 5
MAX_POINT_COUNT = 20

POINT_COLOR_PALETTE: list[tuple[str, tuple[int, int, int]]] = [
    ("red", (231, 76, 60)),
    ("green", (39, 174, 96)),
    ("blue", (52, 152, 219)),
    ("yellow", (241, 196, 15)),
    ("magenta", (155, 89, 182)),
    ("cyan", (26, 188, 156)),
    ("orange", (230, 126, 34)),
    ("violet", (142, 68, 173)),
    ("navy", (52, 73, 94)),
    ("lime", (127, 179, 41)),
]

POINT_COLORS: dict[int, tuple[str, tuple[int, int, int]]] = {
    index + 1: color for index, color in enumerate(POINT_COLOR_PALETTE[:DEFAULT_POINT_COUNT])
}

STATIC_LABEL_HEADER = [
    "action",
    "action_slug",
    "role",
    "rank",
    "object_category",
    "wnid",
    "difficulty",
    "difficulty_rank",
    "source_image_path",
    "dataset_image_path",
    "dominant_cluster_ratio",
    "fit_distance",
    "mirror_margin",
    "was_reflected",
]


def point_color(point_id: int) -> tuple[str, tuple[int, int, int]]:
    """Return a stable display color for any positive point id."""
    if point_id <= 0:
        raise ValueError("point_id must be positive")
    if point_id <= len(POINT_COLOR_PALETTE):
        return POINT_COLOR_PALETTE[point_id - 1]

    hue = (point_id * 0.61803398875) % 1.0
    red, green, blue = colorsys.hsv_to_rgb(hue, 0.65, 0.9)
    return (
        f"color_{point_id}",
        (int(red * 255), int(green * 255), int(blue * 255)),
    )


def clamp_point_count(point_count: int) -> int:
    return max(1, min(MAX_POINT_COUNT, int(point_count)))


def point_columns(point_count: int) -> list[str]:
    columns: list[str] = []
    for point_id in range(1, clamp_point_count(point_count) + 1):
        columns.extend([f"p{point_id}_x", f"p{point_id}_y"])
    return columns


def label_header(point_count: int = DEFAULT_POINT_COUNT) -> list[str]:
    return [*STATIC_LABEL_HEADER, *point_columns(point_count)]


LABEL_HEADER = label_header(DEFAULT_POINT_COUNT)

VGM_HEADER = [
    "action",
    "action_slug",
    "reference_rank",
    "reference_object_category",
    "reference_source_image_path",
    "reference_dataset_image_path",
    "reference_overlay_image_path",
    "test_rank",
    "test_object_category",
    "test_source_image_path",
    "test_dataset_image_path",
    "test_overlay_image_path",
    "point_id",
    "point_color_name",
    "point_color_rgb",
    "reference_point_x",
    "reference_point_y",
    "test_point_x",
    "test_point_y",
    "reference_point_x_px",
    "reference_point_y_px",
    "test_point_x_px",
    "test_point_y_px",
]

CAPTION_KEYS = [
    "action",
    "action_slug",
    "role",
    "rank",
    "object_category",
    "dataset_image_path",
    "caption",
]

ACTION_NAME_OVERRIDES = {
    "Brush_Dust": "Brush/Dust",
    "Lift_Something": "Lift Something",
    "Mash_Pound": "Mash/Pound",
    "Pull_out_a_nail": "Pull out a nail",
}


def discover_actions(dataset_root: Path) -> list[str]:
    """Return action slugs that have the expected dataset subfolders."""
    actions: list[str] = []
    for child in dataset_root.iterdir():
        if not child.is_dir() or child.name.startswith("."):
            continue
        if (child / "references").is_dir() and (child / "tests").is_dir():
            actions.append(child.name)
    return sorted(actions)


def ensure_action_layout(dataset_root: Path, action_slug: str) -> None:
    """Create the standard action folders when a new action is selected."""
    action_dir = dataset_root / action_slug
    for folder in ("references", "tests", "reference_overlays", "test_overlays"):
        (action_dir / folder).mkdir(parents=True, exist_ok=True)


def list_image_files(folder: Path) -> list[Path]:
    """Return supported image files in deterministic order."""
    if not folder.exists():
        return []
    return sorted(
        (
            path
            for path in folder.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ),
        key=lambda path: natural_sort_key(path.name),
    )


def natural_sort_key(value: str) -> list[object]:
    return [
        int(part) if part.isdigit() else part.lower()
        for part in re.split(r"(\d+)", value)
    ]


def merge_headers(*headers: list[str] | tuple[str, ...]) -> list[str]:
    merged: list[str] = []
    for header in headers:
        for column in header:
            if column not in merged:
                merged.append(column)
    return merged


def max_point_id_from_columns(columns: list[str] | tuple[str, ...]) -> int:
    max_point_id = 0
    for column in columns:
        match = re.fullmatch(r"p(?P<point_id>\d+)_[xy]", column)
        if match:
            max_point_id = max(max_point_id, int(match.group("point_id")))
    return max_point_id


def max_labeled_point_id(rows: list[dict[str, str]]) -> int:
    max_point_id = 0
    for row in rows:
        for column, value in row.items():
            if value == "":
                continue
            match = re.fullmatch(r"p(?P<point_id>\d+)_[xy]", column)
            if match:
                max_point_id = max(max_point_id, int(match.group("point_id")))
    return max_point_id


def label_header_for_rows(
    point_count: int,
    rows: list[dict[str, str]],
    extra_row: dict[str, str] | None = None,
) -> list[str]:
    labeled_count = max_labeled_point_id(rows)
    if extra_row:
        labeled_count = max(labeled_count, max_labeled_point_id([extra_row]))
    return label_header(max(point_count, labeled_count))


def infer_csv_point_count(path: Path) -> int | None:
    if not path.exists():
        return None
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return None
    point_count = max_point_id_from_columns(tuple(header))
    return point_count or None


def infer_action_point_count(
    dataset_root: Path,
    action_slug: str,
    default: int = DEFAULT_POINT_COUNT,
) -> int:
    counts = [
        count
        for role in ("reference", "test")
        if (count := infer_csv_point_count(label_csv_path(dataset_root, action_slug, role)))
    ]
    if not counts:
        return clamp_point_count(default)
    return clamp_point_count(max(counts))


def read_csv_rows(path: Path, header: list[str]) -> list[dict[str, str]]:
    """Read a known-schema CSV, normalizing missing columns to empty strings."""
    if not path.exists():
        return []

    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return []
        columns = merge_headers(header, tuple(reader.fieldnames))
        return [
            {column: row.get(column, "") or "" for column in columns}
            for row in reader
        ]


def write_csv_rows(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    """Write a known-schema CSV with stable column order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in header})


def yaml_quote(value: str) -> str:
    value = " ".join(value.splitlines())
    return "'" + value.replace("'", "''") + "'"


def yaml_unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def caption_yaml_path(dataset_root: Path, action_slug: str) -> Path:
    return dataset_root / action_slug / "caption.yaml"


def read_caption_entries(path: Path) -> list[dict[str, str]]:
    """Read the simple caption.yaml format produced by this tool."""
    if not path.exists():
        return []

    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.startswith("  - ") and not raw_line.startswith("    "):
            continue

        line = raw_line.strip()
        if line.startswith("- "):
            if current is not None:
                entries.append({key: current.get(key, "") for key in CAPTION_KEYS})
            current = {key: "" for key in CAPTION_KEYS}
            line = line[2:]

        if current is None or ":" not in line:
            continue

        key, value = line.split(":", 1)
        key = key.strip()
        if key in CAPTION_KEYS:
            current[key] = yaml_unquote(value)

    if current is not None:
        entries.append({key: current.get(key, "") for key in CAPTION_KEYS})
    return entries


def write_caption_yaml(path: Path, action_slug: str, entries: list[dict[str, str]]) -> None:
    """Write image captions as an action-level YAML manifest."""
    normalized = [{key: entry.get(key, "") for key in CAPTION_KEYS} for entry in entries]
    action_name = next(
        (entry["action"] for entry in normalized if entry.get("action")),
        ACTION_NAME_OVERRIDES.get(action_slug, action_slug.replace("_", " ")),
    )

    lines = [
        f"action: {yaml_quote(action_name)}",
        f"action_slug: {yaml_quote(action_slug)}",
        "images:",
    ]
    for entry in sorted(normalized, key=lambda item: item.get("dataset_image_path", "")):
        lines.append(f"  - dataset_image_path: {yaml_quote(entry['dataset_image_path'])}")
        for key in CAPTION_KEYS:
            if key == "dataset_image_path":
                continue
            lines.append(f"    {key}: {yaml_quote(entry.get(key, ''))}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def upsert_caption_entries(
    entries: list[dict[str, str]],
    replacements: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Insert or replace caption entries by dataset_image_path."""
    by_path = {
        entry.get("dataset_image_path", ""): {key: entry.get(key, "") for key in CAPTION_KEYS}
        for entry in entries
        if entry.get("dataset_image_path")
    }
    for replacement in replacements:
        dataset_image_path_value = replacement.get("dataset_image_path", "")
        if not dataset_image_path_value:
            continue
        by_path[dataset_image_path_value] = {
            key: replacement.get(key, "") for key in CAPTION_KEYS
        }
    return [by_path[key] for key in sorted(by_path)]


def caption_entry_from_label_row(row: dict[str, str], caption: str) -> dict[str, str]:
    return {
        "action": row.get("action", ""),
        "action_slug": row.get("action_slug", ""),
        "role": row.get("role", ""),
        "rank": row.get("rank", ""),
        "object_category": row.get("object_category", ""),
        "dataset_image_path": row.get("dataset_image_path", ""),
        "caption": caption.strip(),
    }


def save_caption_entries(
    dataset_root: Path,
    action_slug: str,
    replacements: list[dict[str, str]],
) -> int:
    path = caption_yaml_path(dataset_root, action_slug)
    entries = upsert_caption_entries(read_caption_entries(path), replacements)
    write_caption_yaml(path, action_slug, entries)
    return len(entries)


def caption_by_dataset_path(path: Path, dataset_image_path_value: str) -> str:
    for entry in read_caption_entries(path):
        if entry.get("dataset_image_path") == dataset_image_path_value:
            return entry.get("caption", "")
    return ""


def label_csv_path(dataset_root: Path, action_slug: str, role: Role) -> Path:
    filename = "references.csv" if role == "reference" else "tests.csv"
    return dataset_root / action_slug / filename


def action_display_name(dataset_root: Path, action_slug: str) -> str:
    """Prefer existing CSV action names, then fall back to known slug mapping."""
    for role in ("reference", "test"):
        for row in read_csv_rows(label_csv_path(dataset_root, action_slug, role), LABEL_HEADER):
            if row.get("action"):
                return row["action"]
    return ACTION_NAME_OVERRIDES.get(action_slug, action_slug.replace("_", " "))


def dataset_relative_path(dataset_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(dataset_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def parse_rank_and_category(image_path: Path, fallback_rank: int) -> tuple[int, str]:
    """Infer rank/object category from names like 01__spoon__0006.jpg."""
    match = re.match(r"^(?P<rank>\d+)__(?P<category>.+?)__(?P<rest>.+)$", image_path.stem)
    if not match:
        trailing_digits = re.search(r"(?P<rank>\d+)$", image_path.stem)
        if trailing_digits:
            return int(trailing_digits.group("rank")), image_path.stem
        return fallback_rank, image_path.stem
    return int(match.group("rank")), match.group("category")


def format_coord(value: float) -> str:
    return f"{value:.12g}"


def format_pixel(value: float) -> str:
    return str(round(value, 3))


def build_label_row(
    dataset_root: Path,
    action_slug: str,
    role: Role,
    image_path: Path,
    points: dict[int, tuple[float, float]],
    fallback_rank: int,
    existing_row: dict[str, str] | None = None,
    point_count: int = DEFAULT_POINT_COUNT,
) -> dict[str, str]:
    """Create or update one references/tests.csv row for a labeled image."""
    rank, object_category = parse_rank_and_category(image_path, fallback_rank)
    dataset_path = dataset_relative_path(dataset_root, image_path)
    header = merge_headers(label_header(point_count), tuple(existing_row.keys()) if existing_row else ())
    base = {column: "" for column in header}
    if existing_row:
        base.update({column: existing_row.get(column, "") for column in header})

    base.update(
        {
            "action": base.get("action") or action_display_name(dataset_root, action_slug),
            "action_slug": action_slug,
            "role": role,
            "rank": base.get("rank") or str(rank),
            "object_category": base.get("object_category") or object_category,
            "difficulty": base.get("difficulty") or "manual",
            "source_image_path": base.get("source_image_path") or dataset_path,
            "dataset_image_path": dataset_path,
            "was_reflected": base.get("was_reflected") or "0",
        }
    )

    for point_id in range(1, clamp_point_count(point_count) + 1):
        x_key = f"p{point_id}_x"
        y_key = f"p{point_id}_y"
        if point_id in points:
            x_value, y_value = points[point_id]
            base[x_key] = format_coord(x_value)
            base[y_key] = format_coord(y_value)

    return {column: base.get(column, "") for column in header}


def upsert_label_row(
    rows: list[dict[str, str]],
    replacement: dict[str, str],
    header: list[str] | None = None,
) -> list[dict[str, str]]:
    """Insert or replace a label row by dataset_image_path."""
    columns = merge_headers(header or LABEL_HEADER, tuple(replacement.keys()))
    replacement_key = replacement.get("dataset_image_path")
    updated: list[dict[str, str]] = []
    replaced = False

    for row in rows:
        columns = merge_headers(columns, tuple(row.keys()))
        if row.get("dataset_image_path") == replacement_key:
            merged = {column: row.get(column, "") for column in columns}
            merged.update({column: replacement.get(column, "") for column in columns})
            updated.append(merged)
            replaced = True
        else:
            updated.append({column: row.get(column, "") for column in columns})

    if not replaced:
        updated.append({column: replacement.get(column, "") for column in columns})

    return updated


def find_label_row(
    rows: list[dict[str, str]], dataset_image_path_value: str
) -> dict[str, str] | None:
    for row in rows:
        if row.get("dataset_image_path") == dataset_image_path_value:
            return row
    return None


def points_from_row(
    row: dict[str, str] | None,
    point_count: int | None = None,
) -> dict[int, tuple[float, float]]:
    points: dict[int, tuple[float, float]] = {}
    if row is None:
        return points

    active_point_count = (
        clamp_point_count(point_count)
        if point_count is not None
        else max_point_id_from_columns(tuple(row.keys()))
    )
    for point_id in range(1, active_point_count + 1):
        try:
            x_value = row[f"p{point_id}_x"]
            y_value = row[f"p{point_id}_y"]
            if x_value == "" or y_value == "":
                continue
            points[point_id] = (float(x_value), float(y_value))
        except (KeyError, ValueError):
            continue
    return points


def row_has_all_points(row: dict[str, str], point_count: int = DEFAULT_POINT_COUNT) -> bool:
    return len(points_from_row(row, point_count)) == clamp_point_count(point_count)


def sanitized_name(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return clean.strip("_") or "object"


def overlay_rel_path(row: dict[str, str], role: Role) -> str:
    action_slug = row["action_slug"]
    rank = int(row.get("rank") or 0)
    object_category = sanitized_name(row.get("object_category") or "object")
    if role == "reference":
        return f"{action_slug}/reference_overlays/ref{rank:02d}_{object_category}.png"
    return f"{action_slug}/test_overlays/test{rank:02d}_{object_category}.png"


def generate_vgm_rows(
    action_slug: str,
    references: list[dict[str, str]],
    tests: list[dict[str, str]],
    image_size_lookup: Callable[[str], tuple[int, int]],
    point_count: int = DEFAULT_POINT_COUNT,
) -> list[dict[str, str]]:
    """Expand complete reference/test rows into VGM examples."""
    active_point_count = clamp_point_count(point_count)
    rows: list[dict[str, str]] = []
    for reference in references:
        if not row_has_all_points(reference, active_point_count):
            continue
        ref_points = points_from_row(reference, active_point_count)
        ref_width, ref_height = image_size_lookup(reference["dataset_image_path"])

        for test in tests:
            if not row_has_all_points(test, active_point_count):
                continue
            test_points = points_from_row(test, active_point_count)
            test_width, test_height = image_size_lookup(test["dataset_image_path"])

            for point_id in range(1, active_point_count + 1):
                color_name, color_rgb = point_color(point_id)
                ref_x, ref_y = ref_points[point_id]
                test_x, test_y = test_points[point_id]
                rows.append(
                    {
                        "action": reference.get("action") or action_display_name(Path("."), action_slug),
                        "action_slug": action_slug,
                        "reference_rank": reference["rank"],
                        "reference_object_category": reference["object_category"],
                        "reference_source_image_path": reference.get("source_image_path", ""),
                        "reference_dataset_image_path": reference["dataset_image_path"],
                        "reference_overlay_image_path": overlay_rel_path(reference, "reference"),
                        "test_rank": test["rank"],
                        "test_object_category": test["object_category"],
                        "test_source_image_path": test.get("source_image_path", ""),
                        "test_dataset_image_path": test["dataset_image_path"],
                        "test_overlay_image_path": overlay_rel_path(test, "test"),
                        "point_id": str(point_id),
                        "point_color_name": color_name,
                        "point_color_rgb": ",".join(str(channel) for channel in color_rgb),
                        "reference_point_x": format_coord(ref_x),
                        "reference_point_y": format_coord(ref_y),
                        "test_point_x": format_coord(test_x),
                        "test_point_y": format_coord(test_y),
                        "reference_point_x_px": format_pixel(ref_x * ref_width),
                        "reference_point_y_px": format_pixel(ref_y * ref_height),
                        "test_point_x_px": format_pixel(test_x * test_width),
                        "test_point_y_px": format_pixel(test_y * test_height),
                    }
                )
    return rows


def save_action_vgm_csv(
    dataset_root: Path,
    action_slug: str,
    point_count: int | None = None,
) -> int:
    active_point_count = (
        clamp_point_count(point_count)
        if point_count is not None
        else infer_action_point_count(dataset_root, action_slug)
    )
    references = read_csv_rows(
        dataset_root / action_slug / "references.csv",
        label_header(active_point_count),
    )
    tests = read_csv_rows(
        dataset_root / action_slug / "tests.csv",
        label_header(active_point_count),
    )

    def image_size_lookup(dataset_image_path_value: str) -> tuple[int, int]:
        if Image is None:
            raise RuntimeError("Pillow is required to calculate image sizes.")
        with Image.open(dataset_root / dataset_image_path_value) as image:
            return image.size

    rows = generate_vgm_rows(
        action_slug,
        references,
        tests,
        image_size_lookup,
        point_count=active_point_count,
    )
    write_csv_rows(dataset_root / action_slug / "vgm_examples.csv", VGM_HEADER, rows)
    return len(rows)


def render_overlay(
    image_path: Path,
    points: dict[int, tuple[float, float]],
    output_path: Path,
) -> None:
    if Image is None or ImageDraw is None:
        raise RuntimeError("Pillow is required to render overlays.")

    with Image.open(image_path) as image:
        overlay = image.convert("RGB")
    draw = ImageDraw.Draw(overlay)
    width, height = overlay.size
    radius = max(5, min(width, height) // 70)
    label_offset = radius + 2

    for point_id, (x_norm, y_norm) in sorted(points.items()):
        color_name, color_rgb = point_color(point_id)
        del color_name
        x_value = max(0.0, min(1.0, x_norm)) * width
        y_value = max(0.0, min(1.0, y_norm)) * height
        left = x_value - radius
        top = y_value - radius
        right = x_value + radius
        bottom = y_value + radius
        draw.ellipse((left, top, right, bottom), fill=color_rgb, outline=(0, 0, 0), width=2)
        draw.text(
            (x_value + label_offset, y_value + label_offset),
            str(point_id),
            fill=(0, 0, 0),
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    overlay.save(output_path)


class PointLabelerApp:
    def __init__(
        self,
        dataset_root: Path,
        initial_action: str | None = None,
        initial_point_count: int | None = None,
    ) -> None:
        if tk is None or ttk is None or messagebox is None:
            raise RuntimeError("tkinter is required to run the point labeler GUI.")
        if Image is None or ImageTk is None:
            raise RuntimeError("Pillow is required to run the point labeler GUI.")

        self.dataset_root = dataset_root.resolve()
        self.initial_point_count = initial_point_count
        self.window = tk.Tk()
        self.window.title("FunKPoint Point Labeler")
        self.window.geometry("1280x820")
        self.window.minsize(960, 640)

        self.action_var = tk.StringVar(value=initial_action or "")
        self.reference_var = tk.StringVar()
        self.test_var = tk.StringVar()
        self.point_var = tk.IntVar(value=1)
        self.point_count_var = tk.IntVar(
            value=clamp_point_count(initial_point_count or DEFAULT_POINT_COUNT)
        )
        self.status_var = tk.StringVar(value="")

        self.reference_images: list[Path] = []
        self.test_images: list[Path] = []
        self.current_paths: dict[Role, Path | None] = {"reference": None, "test": None}
        self.points: dict[Role, dict[int, tuple[float, float]]] = {
            "reference": {},
            "test": {},
        }
        self.display_state: dict[Role, dict[str, object]] = {
            "reference": {},
            "test": {},
        }

        self._build_ui()
        self._load_actions(initial_action)
        self._bind_shortcuts()

    def _build_ui(self) -> None:
        top = ttk.Frame(self.window, padding=(10, 8))
        top.pack(fill=tk.X)

        ttk.Label(top, text="Action").pack(side=tk.LEFT)
        self.action_combo = ttk.Combobox(
            top,
            textvariable=self.action_var,
            state="readonly",
            width=24,
        )
        self.action_combo.pack(side=tk.LEFT, padx=(6, 16))
        self.action_combo.bind("<<ComboboxSelected>>", self._on_action_changed)

        ttk.Button(top, text="Refresh", command=self._refresh_current_action).pack(
            side=tk.LEFT,
            padx=(0, 16),
        )

        ttk.Label(top, text="Reference").pack(side=tk.LEFT)
        self.reference_combo = ttk.Combobox(
            top,
            textvariable=self.reference_var,
            state="readonly",
            width=34,
        )
        self.reference_combo.pack(side=tk.LEFT, padx=(6, 16))
        self.reference_combo.bind("<<ComboboxSelected>>", self._on_reference_changed)

        ttk.Label(top, text="Test").pack(side=tk.LEFT)
        self.test_combo = ttk.Combobox(
            top,
            textvariable=self.test_var,
            state="readonly",
            width=34,
        )
        self.test_combo.pack(side=tk.LEFT, padx=(6, 0))
        self.test_combo.bind("<<ComboboxSelected>>", self._on_test_changed)

        controls = ttk.Frame(self.window, padding=(10, 0, 10, 8))
        controls.pack(fill=tk.X)

        point_frame = ttk.Frame(controls)
        point_frame.pack(side=tk.LEFT)
        ttk.Label(point_frame, text="Point count").pack(side=tk.LEFT, padx=(0, 6))
        self.point_count_spinbox = tk.Spinbox(
            point_frame,
            from_=1,
            to=MAX_POINT_COUNT,
            width=4,
            textvariable=self.point_count_var,
            command=self._on_point_count_changed,
        )
        self.point_count_spinbox.pack(side=tk.LEFT, padx=(0, 16))
        self.point_count_spinbox.bind("<FocusOut>", lambda _event: self._on_point_count_changed())
        self.point_count_spinbox.bind("<Return>", lambda _event: self._on_point_count_changed())

        ttk.Label(point_frame, text="Point").pack(side=tk.LEFT, padx=(0, 6))
        self.point_spinbox = tk.Spinbox(
            point_frame,
            from_=1,
            to=self._point_count(),
            width=4,
            textvariable=self.point_var,
            command=self._on_point_changed,
        )
        self.point_spinbox.pack(side=tk.LEFT, padx=(0, 8))
        self.point_spinbox.bind("<FocusOut>", lambda _event: self._on_point_changed())
        self.point_spinbox.bind("<Return>", lambda _event: self._on_point_changed())
        self.point_color_label = ttk.Label(point_frame, text="")
        self.point_color_label.pack(side=tk.LEFT)

        action_buttons = ttk.Frame(controls)
        action_buttons.pack(side=tk.RIGHT)
        ttk.Button(action_buttons, text="Clear Point", command=self._clear_current_point).pack(
            side=tk.LEFT,
            padx=4,
        )
        ttk.Button(action_buttons, text="Clear Pair", command=self._clear_pair).pack(
            side=tk.LEFT,
            padx=4,
        )
        ttk.Button(action_buttons, text="Regenerate VGM", command=self._regenerate_vgm).pack(
            side=tk.LEFT,
            padx=4,
        )
        ttk.Button(action_buttons, text="Save Captions", command=self._save_captions).pack(
            side=tk.LEFT,
            padx=4,
        )
        ttk.Button(action_buttons, text="Save Pair", command=self._save_pair).pack(
            side=tk.LEFT,
            padx=4,
        )

        captions = ttk.Frame(self.window, padding=(10, 0, 10, 8))
        captions.pack(fill=tk.X)
        captions.columnconfigure(0, weight=1)
        captions.columnconfigure(1, weight=1)

        ttk.Label(captions, text="Reference caption").grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 5),
        )
        ttk.Label(captions, text="Test caption").grid(
            row=0,
            column=1,
            sticky="w",
            padx=(5, 0),
        )
        self.reference_caption_text = tk.Text(captions, height=3, wrap=tk.WORD)
        self.reference_caption_text.grid(row=1, column=0, sticky="ew", padx=(0, 5))
        self.test_caption_text = tk.Text(captions, height=3, wrap=tk.WORD)
        self.test_caption_text.grid(row=1, column=1, sticky="ew", padx=(5, 0))

        panels = ttk.Frame(self.window, padding=(10, 0, 10, 8))
        panels.pack(fill=tk.BOTH, expand=True)
        panels.columnconfigure(0, weight=1)
        panels.columnconfigure(1, weight=1)
        panels.rowconfigure(1, weight=1)

        ttk.Label(panels, text="Reference", anchor=tk.CENTER).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 5),
        )
        ttk.Label(panels, text="Test", anchor=tk.CENTER).grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(5, 0),
        )

        self.reference_canvas = tk.Canvas(panels, bg="#f5f5f5", highlightthickness=1)
        self.reference_canvas.grid(row=1, column=0, sticky="nsew", padx=(0, 5))
        self.reference_canvas.bind("<Button-1>", lambda event: self._mark_point("reference", event))
        self.reference_canvas.bind("<Configure>", lambda event: self._redraw_panel("reference"))

        self.test_canvas = tk.Canvas(panels, bg="#f5f5f5", highlightthickness=1)
        self.test_canvas.grid(row=1, column=1, sticky="nsew", padx=(5, 0))
        self.test_canvas.bind("<Button-1>", lambda event: self._mark_point("test", event))
        self.test_canvas.bind("<Configure>", lambda event: self._redraw_panel("test"))

        status = ttk.Label(
            self.window,
            textvariable=self.status_var,
            anchor=tk.W,
            padding=(10, 6),
        )
        status.pack(fill=tk.X)

    def _bind_shortcuts(self) -> None:
        self.window.bind("<Control-s>", lambda _event: self._save_pair())
        self.window.bind("<Control-r>", lambda _event: self._refresh_current_action())
        for point_id in range(1, min(9, MAX_POINT_COUNT) + 1):
            self.window.bind(str(point_id), lambda _event, value=point_id: self._select_point(value))

    def _point_count(self) -> int:
        try:
            point_count = int(self.point_count_var.get())
        except (tk.TclError, ValueError):
            point_count = DEFAULT_POINT_COUNT
        point_count = clamp_point_count(point_count)
        try:
            current_value = self.point_count_var.get()
        except tk.TclError:
            current_value = None
        if current_value != point_count:
            self.point_count_var.set(point_count)
        return point_count

    def _selected_point(self) -> int:
        try:
            point_id = int(self.point_var.get())
        except (tk.TclError, ValueError):
            point_id = 1
        point_id = max(1, min(self._point_count(), point_id))
        try:
            current_value = self.point_var.get()
        except tk.TclError:
            current_value = None
        if current_value != point_id:
            self.point_var.set(point_id)
        return point_id

    def _select_point(self, point_id: int) -> None:
        self.point_var.set(max(1, min(self._point_count(), point_id)))
        self._update_status()

    def _on_point_changed(self) -> None:
        self._selected_point()
        self._update_status()

    def _on_point_count_changed(self) -> None:
        point_count = self._point_count()
        self.point_spinbox.configure(to=point_count)
        self._selected_point()
        for role in ("reference", "test"):
            self.points[role] = {
                point_id: coords
                for point_id, coords in self.points[role].items()
                if point_id <= point_count
            }
            self._redraw_panel(role)
        self._update_status()

    def _load_actions(self, initial_action: str | None) -> None:
        actions = discover_actions(self.dataset_root)
        self.action_combo["values"] = actions
        if not actions:
            self._set_status("No action folders found.")
            return

        selected = initial_action if initial_action in actions else actions[0]
        self.action_var.set(selected)
        self._load_action_images(selected)

    def _on_action_changed(self, _event: object | None = None) -> None:
        self._load_action_images(self.action_var.get())

    def _refresh_current_action(self) -> None:
        action_slug = self.action_var.get()
        if not action_slug:
            self._load_actions(None)
            return
        ensure_action_layout(self.dataset_root, action_slug)
        self._load_action_images(action_slug)

    def _load_action_images(self, action_slug: str) -> None:
        ensure_action_layout(self.dataset_root, action_slug)
        if self.initial_point_count is not None:
            self.point_count_var.set(clamp_point_count(self.initial_point_count))
            self.initial_point_count = None
        else:
            self.point_count_var.set(infer_action_point_count(self.dataset_root, action_slug))
        self.point_spinbox.configure(to=self._point_count())
        action_dir = self.dataset_root / action_slug
        self.reference_images = list_image_files(action_dir / "references")
        self.test_images = list_image_files(action_dir / "tests")

        self.reference_combo["values"] = [path.name for path in self.reference_images]
        self.test_combo["values"] = [path.name for path in self.test_images]

        self.reference_var.set(self.reference_images[0].name if self.reference_images else "")
        self.test_var.set(self.test_images[0].name if self.test_images else "")
        self._select_image("reference", self.reference_var.get())
        self._select_image("test", self.test_var.get())
        self._update_status()

    def _on_reference_changed(self, _event: object | None = None) -> None:
        self._select_image("reference", self.reference_var.get())
        self._update_status()

    def _on_test_changed(self, _event: object | None = None) -> None:
        self._select_image("test", self.test_var.get())
        self._update_status()

    def _select_image(self, role: Role, filename: str) -> None:
        images = self.reference_images if role == "reference" else self.test_images
        selected = next((path for path in images if path.name == filename), None)
        self.current_paths[role] = selected
        self.points[role] = {}

        if selected is not None:
            point_count = self._point_count()
            rows = read_csv_rows(
                label_csv_path(self.dataset_root, self.action_var.get(), role),
                label_header(point_count),
            )
            dataset_path = dataset_relative_path(self.dataset_root, selected)
            self.points[role] = points_from_row(find_label_row(rows, dataset_path), point_count)
            caption = caption_by_dataset_path(
                caption_yaml_path(self.dataset_root, self.action_var.get()),
                dataset_path,
            )
            self._set_caption_text(role, caption)
        else:
            self._set_caption_text(role, "")

        self._redraw_panel(role)
        self._advance_to_first_incomplete_point()

    def _caption_text(self, role: Role) -> str:
        widget = self._caption_widget_for_role(role)
        return widget.get("1.0", tk.END).strip()

    def _set_caption_text(self, role: Role, caption: str) -> None:
        widget = self._caption_widget_for_role(role)
        widget.delete("1.0", tk.END)
        if caption:
            widget.insert("1.0", caption)

    def _caption_widget_for_role(self, role: Role) -> object:
        return self.reference_caption_text if role == "reference" else self.test_caption_text

    def _redraw_panel(self, role: Role) -> None:
        canvas = self._canvas_for_role(role)
        canvas.delete("all")
        image_path = self.current_paths[role]
        if image_path is None:
            canvas.create_text(
                canvas.winfo_width() // 2,
                canvas.winfo_height() // 2,
                text=f"No {role} image",
                fill="#555555",
            )
            self.display_state[role] = {}
            return

        canvas_width = max(canvas.winfo_width(), 1)
        canvas_height = max(canvas.winfo_height(), 1)
        with Image.open(image_path) as source:
            image = source.convert("RGB")

        original_width, original_height = image.size
        scale = min(
            (canvas_width - 20) / original_width,
            (canvas_height - 20) / original_height,
        )
        scale = max(scale, 0.01)
        display_width = max(1, int(original_width * scale))
        display_height = max(1, int(original_height * scale))
        display_image = image.resize((display_width, display_height))
        tk_image = ImageTk.PhotoImage(display_image)
        x_offset = (canvas_width - display_width) // 2
        y_offset = (canvas_height - display_height) // 2

        canvas.create_image(x_offset, y_offset, anchor=tk.NW, image=tk_image)
        self.display_state[role] = {
            "image": tk_image,
            "x_offset": x_offset,
            "y_offset": y_offset,
            "display_width": display_width,
            "display_height": display_height,
            "original_width": original_width,
            "original_height": original_height,
        }

        radius = 7
        for point_id, (x_norm, y_norm) in sorted(self.points[role].items()):
            color_name, rgb = point_color(point_id)
            del color_name
            x_value = x_offset + x_norm * display_width
            y_value = y_offset + y_norm * display_height
            canvas.create_oval(
                x_value - radius,
                y_value - radius,
                x_value + radius,
                y_value + radius,
                fill=self._hex_color(rgb),
                outline="#111111",
                width=2,
            )
            canvas.create_text(
                x_value + radius + 7,
                y_value + radius + 7,
                text=str(point_id),
                fill="#111111",
            )

    def _mark_point(self, role: Role, event: object) -> None:
        state = self.display_state.get(role) or {}
        if not state:
            return

        x_offset = int(state["x_offset"])
        y_offset = int(state["y_offset"])
        display_width = int(state["display_width"])
        display_height = int(state["display_height"])
        x_value = getattr(event, "x") - x_offset
        y_value = getattr(event, "y") - y_offset

        if x_value < 0 or y_value < 0 or x_value > display_width or y_value > display_height:
            return

        point_id = self._selected_point()
        self.points[role][point_id] = (
            max(0.0, min(1.0, x_value / display_width)),
            max(0.0, min(1.0, y_value / display_height)),
        )
        self._advance_to_first_incomplete_point()
        self._redraw_panel(role)
        self._update_status()

    def _clear_current_point(self) -> None:
        point_id = self._selected_point()
        for role in ("reference", "test"):
            self.points[role].pop(point_id, None)
            self._redraw_panel(role)
        self._update_status()

    def _clear_pair(self) -> None:
        self.points = {"reference": {}, "test": {}}
        self.point_var.set(1)
        self._redraw_panel("reference")
        self._redraw_panel("test")
        self._update_status()

    def _save_pair(self) -> None:
        action_slug = self.action_var.get()
        if not action_slug:
            self._show_error("Select an action before saving.")
            return
        if self.current_paths["reference"] is None or self.current_paths["test"] is None:
            self._show_error("Select both a reference image and a test image.")
            return
        point_count = self._point_count()
        reference_points = {
            point_id: coords
            for point_id, coords in self.points["reference"].items()
            if point_id <= point_count
        }
        test_points = {
            point_id: coords
            for point_id, coords in self.points["test"].items()
            if point_id <= point_count
        }
        if (
            len(reference_points) != point_count
            or len(test_points) != point_count
        ):
            self._show_error(f"Mark all {point_count} points on both images before saving.")
            return

        saved_rows: dict[Role, dict[str, str]] = {}
        for role in ("reference", "test"):
            image_path = self.current_paths[role]
            if image_path is None:
                continue
            rows = read_csv_rows(
                label_csv_path(self.dataset_root, action_slug, role),
                label_header(point_count),
            )
            dataset_path = dataset_relative_path(self.dataset_root, image_path)
            existing = find_label_row(rows, dataset_path)
            fallback_rank = self._fallback_rank(role, image_path)
            replacement = build_label_row(
                dataset_root=self.dataset_root,
                action_slug=action_slug,
                role=role,
                image_path=image_path,
                points=reference_points if role == "reference" else test_points,
                fallback_rank=fallback_rank,
                existing_row=existing,
                point_count=point_count,
            )
            header = label_header_for_rows(point_count, rows, replacement)
            rows = upsert_label_row(rows, replacement, header=header)
            write_csv_rows(label_csv_path(self.dataset_root, action_slug, role), header, rows)
            render_overlay(
                image_path=image_path,
                points=reference_points if role == "reference" else test_points,
                output_path=self.dataset_root / overlay_rel_path(replacement, role),
            )
            saved_rows[role] = replacement

        example_count = save_action_vgm_csv(self.dataset_root, action_slug, point_count=point_count)
        caption_count = save_caption_entries(
            self.dataset_root,
            action_slug,
            [
                caption_entry_from_label_row(saved_rows["reference"], self._caption_text("reference")),
                caption_entry_from_label_row(saved_rows["test"], self._caption_text("test")),
            ],
        )
        self._set_status(
            "Saved "
            f"{saved_rows['reference']['dataset_image_path']} and "
            f"{saved_rows['test']['dataset_image_path']}; "
            f"{example_count} VGM rows; {caption_count} captions."
        )

    def _save_captions(self) -> None:
        action_slug = self.action_var.get()
        if not action_slug:
            self._show_error("Select an action before saving captions.")
            return

        replacements: list[dict[str, str]] = []
        for role in ("reference", "test"):
            entry = self._caption_entry_for_current_image(role)
            if entry is not None:
                replacements.append(entry)

        if not replacements:
            self._show_error("Select at least one image before saving captions.")
            return

        caption_count = save_caption_entries(self.dataset_root, action_slug, replacements)
        self._set_status(f"Saved {len(replacements)} caption updates; {caption_count} caption entries.")

    def _caption_entry_for_current_image(self, role: Role) -> dict[str, str] | None:
        action_slug = self.action_var.get()
        image_path = self.current_paths[role]
        if not action_slug or image_path is None:
            return None

        point_count = self._point_count()
        rows = read_csv_rows(
            label_csv_path(self.dataset_root, action_slug, role),
            label_header(point_count),
        )
        dataset_path = dataset_relative_path(self.dataset_root, image_path)
        row = find_label_row(rows, dataset_path)
        if row is None:
            row = build_label_row(
                dataset_root=self.dataset_root,
                action_slug=action_slug,
                role=role,
                image_path=image_path,
                points={},
                fallback_rank=self._fallback_rank(role, image_path),
                point_count=point_count,
            )
        return caption_entry_from_label_row(row, self._caption_text(role))

    def _regenerate_vgm(self) -> None:
        action_slug = self.action_var.get()
        if not action_slug:
            self._show_error("Select an action first.")
            return
        try:
            example_count = save_action_vgm_csv(
                self.dataset_root,
                action_slug,
                point_count=self._point_count(),
            )
        except FileNotFoundError as exc:
            self._show_error(f"Missing image referenced by CSV: {exc}")
            return
        self._set_status(f"Regenerated {action_slug}/vgm_examples.csv with {example_count} rows.")

    def _fallback_rank(self, role: Role, image_path: Path) -> int:
        images = self.reference_images if role == "reference" else self.test_images
        try:
            return images.index(image_path) + 1
        except ValueError:
            return 1

    def _advance_to_first_incomplete_point(self) -> None:
        current = self._selected_point()
        if current not in self.points["reference"] or current not in self.points["test"]:
            return

        for point_id in range(1, self._point_count() + 1):
            if point_id not in self.points["reference"] or point_id not in self.points["test"]:
                self.point_var.set(point_id)
                return

    def _update_status(self) -> None:
        action_slug = self.action_var.get() or "No action"
        point_count = self._point_count()
        selected_point = self._selected_point()
        color_name, rgb = point_color(selected_point)
        self.point_color_label.configure(
            text=color_name,
            foreground=self._hex_color(rgb),
        )
        ref_count = len([point_id for point_id in self.points["reference"] if point_id <= point_count])
        test_count = len([point_id for point_id in self.points["test"] if point_id <= point_count])
        self._set_status(
            f"{action_slug}: point {selected_point} of {point_count} selected; "
            f"reference {ref_count}/{point_count}, test {test_count}/{point_count}."
        )

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    def _show_error(self, message: str) -> None:
        messagebox.showerror("Point Labeler", message)
        self._set_status(message)

    def _canvas_for_role(self, role: Role) -> object:
        return self.reference_canvas if role == "reference" else self.test_canvas

    @staticmethod
    def _hex_color(rgb: tuple[int, int, int]) -> str:
        return "#{:02x}{:02x}{:02x}".format(*rgb)

    def run(self) -> None:
        self.window.mainloop()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mark corresponding FunKPoint keypoints for reference/test images.",
    )
    parser.add_argument(
        "--dataset-root",
        type=Path,
        default=Path.cwd(),
        help="Dataset root containing action folders. Defaults to the current directory.",
    )
    parser.add_argument(
        "--action",
        default=None,
        help="Initial action slug to open, for example Hooking or Dagging.",
    )
    parser.add_argument(
        "--points",
        type=int,
        default=None,
        help=f"Initial point count for the action, from 1 to {MAX_POINT_COUNT}.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        PointLabelerApp(args.dataset_root, args.action, args.points).run()
    except RuntimeError as exc:
        print(f"point_labeler_gui.py: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
