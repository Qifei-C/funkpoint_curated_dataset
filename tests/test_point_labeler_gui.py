import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "tools" / "point_labeler_gui.py"
SPEC = importlib.util.spec_from_file_location("point_labeler_gui", MODULE_PATH)
point_labeler_gui = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(point_labeler_gui)


class PointLabelerDataTests(unittest.TestCase):
    def test_discover_actions_requires_dataset_subfolders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for action in ("Hooking", "Dagging"):
                (root / action / "references").mkdir(parents=True)
                (root / action / "tests").mkdir()
            (root / "Not_An_Action").mkdir()

            self.assertEqual(
                point_labeler_gui.discover_actions(root),
                ["Dagging", "Hooking"],
            )

    def test_plain_numbered_filenames_define_rank_and_category(self) -> None:
        self.assertEqual(
            point_labeler_gui.parse_rank_and_category(Path("test10.png"), fallback_rank=2),
            (10, "test10"),
        )
        self.assertEqual(
            point_labeler_gui.parse_rank_and_category(Path("ref2.png"), fallback_rank=9),
            (2, "ref2"),
        )
        self.assertEqual(
            point_labeler_gui.parse_rank_and_category(
                Path("context_vqa/test1_02.png"),
                fallback_rank=9,
            ),
            (1, "test1_02"),
        )

    def test_list_image_files_includes_nested_context_vqa_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "tests" / "context_vqa").mkdir(parents=True)
            (root / "tests" / "test2.png").touch()
            (root / "tests" / "context_vqa" / "test1_02.png").touch()
            (root / "tests" / "context_vqa" / "test1_01.png").touch()

            self.assertEqual(
                [
                    path.relative_to(root / "tests").as_posix()
                    for path in point_labeler_gui.list_image_files(root / "tests")
                ],
                [
                    "context_vqa/test1_01.png",
                    "context_vqa/test1_02.png",
                    "test2.png",
                ],
            )

    def test_image_metadata_uses_filename_convention(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = root / "Hooking" / "references" / "02__hook_tool__0042.JPEG"
            image_path.parent.mkdir(parents=True)
            image_path.touch()

            metadata = point_labeler_gui.build_label_row(
                dataset_root=root,
                action_slug="Hooking",
                role="reference",
                image_path=image_path,
                points={
                    1: (0.1, 0.2),
                    2: (0.2, 0.3),
                    3: (0.3, 0.4),
                    4: (0.4, 0.5),
                    5: (0.5, 0.6),
                },
                fallback_rank=7,
            )

            self.assertEqual(metadata["action"], "Hooking")
            self.assertEqual(metadata["action_slug"], "Hooking")
            self.assertEqual(metadata["role"], "reference")
            self.assertEqual(metadata["rank"], "2")
            self.assertEqual(metadata["object_category"], "hook_tool")
            self.assertEqual(
                metadata["dataset_image_path"],
                "Hooking/references/02__hook_tool__0042.JPEG",
            )
            self.assertEqual(metadata["p5_y"], "0.6")

    def test_build_label_row_supports_four_point_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image_path = root / "Dagging" / "references" / "01__drag_hook__0001.png"
            image_path.parent.mkdir(parents=True)
            image_path.touch()

            metadata = point_labeler_gui.build_label_row(
                dataset_root=root,
                action_slug="Dagging",
                role="reference",
                image_path=image_path,
                points={
                    1: (0.1, 0.2),
                    2: (0.2, 0.3),
                    3: (0.3, 0.4),
                    4: (0.4, 0.5),
                },
                fallback_rank=1,
                point_count=4,
            )

            self.assertEqual(metadata["p4_y"], "0.5")
            self.assertNotIn("p5_x", metadata)

    def test_upsert_row_updates_by_dataset_path(self) -> None:
        existing = [
            {
                **{column: "" for column in point_labeler_gui.LABEL_HEADER},
                "action": "Hooking",
                "action_slug": "Hooking",
                "role": "test",
                "rank": "1",
                "object_category": "hook",
                "dataset_image_path": "Hooking/tests/01__hook__0001.png",
                "difficulty": "manual",
                "p1_x": "0.1",
            }
        ]
        replacement = {
            **existing[0],
            "p1_x": "0.9",
            "p1_y": "0.8",
        }

        updated = point_labeler_gui.upsert_label_row(existing, replacement)

        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]["difficulty"], "manual")
        self.assertEqual(updated[0]["p1_x"], "0.9")
        self.assertEqual(updated[0]["p1_y"], "0.8")

    def test_upsert_row_keeps_same_image_context_annotations_separate(self) -> None:
        existing = [
            {
                **{column: "" for column in point_labeler_gui.LABEL_HEADER},
                "annotation_id": "Dagging/tests/context_vqa/test1_01",
                "dataset_image_path": "Dagging/tests/test1.png",
                "caption": "first",
                "p1_x": "0.1",
            }
        ]
        replacement = {
            **{column: "" for column in point_labeler_gui.LABEL_HEADER},
            "annotation_id": "Dagging/tests/context_vqa/test1_02",
            "dataset_image_path": "Dagging/tests/test1.png",
            "p1_x": "0.9",
        }

        updated = point_labeler_gui.upsert_label_row(existing, replacement)

        self.assertEqual(len(updated), 2)
        self.assertEqual(
            [row["annotation_id"] for row in updated],
            ["Dagging/tests/context_vqa/test1_01", "Dagging/tests/context_vqa/test1_02"],
        )

    def test_generate_vgm_rows_expands_reference_test_points(self) -> None:
        reference = {
            **{column: "" for column in point_labeler_gui.LABEL_HEADER},
            "action": "Hooking",
            "action_slug": "Hooking",
            "role": "reference",
            "rank": "1",
            "object_category": "hook",
            "source_image_path": "source/ref.png",
            "dataset_image_path": "Hooking/references/01__hook__0001.png",
        }
        test = {
            **{column: "" for column in point_labeler_gui.LABEL_HEADER},
            "action": "Hooking",
            "action_slug": "Hooking",
            "role": "test",
            "rank": "2",
            "object_category": "ring",
            "source_image_path": "source/test.png",
            "dataset_image_path": "Hooking/tests/02__ring__0007.png",
        }
        for point_id in range(1, 6):
            reference[f"p{point_id}_x"] = str(point_id / 10)
            reference[f"p{point_id}_y"] = str(point_id / 20)
            test[f"p{point_id}_x"] = str(point_id / 5)
            test[f"p{point_id}_y"] = str(point_id / 10)

        rows = point_labeler_gui.generate_vgm_rows(
            action_slug="Hooking",
            references=[reference],
            tests=[test],
            image_size_lookup=lambda path: (100, 200)
            if "references" in path
            else (300, 400),
        )

        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["reference_overlay_image_path"], "Hooking/reference_overlays/ref01_hook.png")
        self.assertEqual(rows[0]["test_overlay_image_path"], "Hooking/test_overlays/test02_ring.png")
        self.assertEqual(rows[0]["point_color_name"], "red")
        self.assertEqual(rows[4]["reference_point_x_px"], "50.0")
        self.assertEqual(rows[4]["test_point_y_px"], "200.0")

    def test_generate_vgm_rows_honors_smaller_point_count(self) -> None:
        reference = {
            **{column: "" for column in point_labeler_gui.label_header(4)},
            "action": "Dagging",
            "action_slug": "Dagging",
            "role": "reference",
            "rank": "1",
            "object_category": "drag_hook",
            "dataset_image_path": "Dagging/references/01__drag_hook__0001.png",
        }
        test = {
            **{column: "" for column in point_labeler_gui.label_header(4)},
            "action": "Dagging",
            "action_slug": "Dagging",
            "role": "test",
            "rank": "1",
            "object_category": "fabric",
            "dataset_image_path": "Dagging/tests/01__fabric__0002.png",
        }
        for point_id in range(1, 5):
            reference[f"p{point_id}_x"] = str(point_id / 10)
            reference[f"p{point_id}_y"] = str(point_id / 20)
            test[f"p{point_id}_x"] = str(point_id / 5)
            test[f"p{point_id}_y"] = str(point_id / 10)

        rows = point_labeler_gui.generate_vgm_rows(
            action_slug="Dagging",
            references=[reference],
            tests=[test],
            image_size_lookup=lambda _path: (100, 200),
            point_count=4,
        )

        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[-1]["point_id"], "4")

    def test_generate_vgm_rows_supports_more_than_five_points(self) -> None:
        reference = {
            **{column: "" for column in point_labeler_gui.label_header(6)},
            "action": "Hooking",
            "action_slug": "Hooking",
            "role": "reference",
            "rank": "1",
            "object_category": "hook",
            "dataset_image_path": "Hooking/references/01__hook__0001.png",
        }
        test = {
            **{column: "" for column in point_labeler_gui.label_header(6)},
            "action": "Hooking",
            "action_slug": "Hooking",
            "role": "test",
            "rank": "1",
            "object_category": "loop",
            "dataset_image_path": "Hooking/tests/01__loop__0002.png",
        }
        for point_id in range(1, 7):
            reference[f"p{point_id}_x"] = str(point_id / 10)
            reference[f"p{point_id}_y"] = str(point_id / 20)
            test[f"p{point_id}_x"] = str(point_id / 5)
            test[f"p{point_id}_y"] = str(point_id / 10)

        rows = point_labeler_gui.generate_vgm_rows(
            action_slug="Hooking",
            references=[reference],
            tests=[test],
            image_size_lookup=lambda _path: (100, 200),
            point_count=6,
        )

        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[-1]["point_id"], "6")
        self.assertNotEqual(rows[-1]["point_color_rgb"], "")

    def test_caption_json_round_trips_multi_image_captions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            caption_path = root / "Hooking" / "caption.json"
            caption_path.parent.mkdir(parents=True)
            entries = [
                {
                    "action": "Hooking",
                    "action_slug": "Hooking",
                    "role": "reference",
                    "rank": "1",
                    "object_category": "hook",
                    "annotation_id": "",
                    "dataset_image_path": "Hooking/references/01__hook__0001.png",
                    "captions": [
                        "A hook catches the loop from the left side.",
                        "The hook is aligned with the ring.",
                    ],
                },
                {
                    "action": "Hooking",
                    "action_slug": "Hooking",
                    "role": "test",
                    "rank": "1",
                    "object_category": "loop",
                    "annotation_id": "",
                    "dataset_image_path": "Hooking/tests/01__loop__0002.png",
                    "captions": ["The tool hooks and pulls the loop."],
                },
            ]

            point_labeler_gui.write_caption_json(caption_path, "Hooking", entries)
            loaded = point_labeler_gui.read_caption_entries(caption_path)

            self.assertEqual(loaded, entries)
            text = caption_path.read_text(encoding="utf-8")
            self.assertIn('"images"', text)
            self.assertIn('"captions"', text)

    def test_old_caption_yaml_reads_as_single_caption_list(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            caption_path = root / "Hooking" / "caption.yaml"
            caption_path.parent.mkdir(parents=True)
            caption_path.write_text(
                "\n".join(
                    [
                        "action: 'Hooking'",
                        "action_slug: 'Hooking'",
                        "images:",
                        "  - dataset_image_path: 'Hooking/tests/test1.png'",
                        "    action: 'Hooking'",
                        "    action_slug: 'Hooking'",
                        "    role: 'test'",
                        "    rank: '1'",
                        "    object_category: 'test1'",
                        "    annotation_id: ''",
                        "    caption: 'The tool hooks the loop.'",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            entries = point_labeler_gui.read_caption_entries(caption_path)

            self.assertEqual(entries[0]["captions"], ["The tool hooks the loop."])

    def test_upsert_caption_entries_replaces_by_dataset_path(self) -> None:
        entries = [
            {
                "action": "Hooking",
                "action_slug": "Hooking",
                "role": "reference",
                "rank": "1",
                "object_category": "hook",
                "dataset_image_path": "Hooking/references/01__hook__0001.png",
                "captions": ["old caption"],
            }
        ]
        replacement = {
            **entries[0],
            "captions": ["new caption", "alternate caption"],
        }

        updated = point_labeler_gui.upsert_caption_entries(entries, [replacement])

        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]["captions"], ["new caption", "alternate caption"])

    def test_upsert_caption_entries_keeps_same_image_context_annotations_separate(self) -> None:
        entries = [
            {
                "action": "Dagging",
                "action_slug": "Dagging",
                "role": "test",
                "rank": "1",
                "object_category": "test1_01",
                "annotation_id": "Dagging/tests/context_vqa/test1_01",
                "dataset_image_path": "Dagging/tests/test1.png",
                "captions": ["first description"],
            }
        ]
        replacement = {
            **entries[0],
            "annotation_id": "Dagging/tests/context_vqa/test1_02",
            "object_category": "test1_02",
            "captions": ["second description"],
        }

        updated = point_labeler_gui.upsert_caption_entries(entries, [replacement])

        self.assertEqual(len(updated), 2)
        self.assertEqual(
            [entry["captions"] for entry in updated],
            [["first description"], ["second description"]],
        )

    def test_caption_text_uses_non_empty_lines_as_multiple_captions(self) -> None:
        self.assertEqual(
            point_labeler_gui.captions_from_text("first caption\n\n second caption "),
            ["first caption", "second caption"],
        )
        self.assertEqual(
            point_labeler_gui.caption_text_from_captions(["first", "second"]),
            "first\nsecond",
        )


if __name__ == "__main__":
    unittest.main()
