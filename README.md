# FunKPoint Curated Dataset

This dataset was materialized from `labels.csv` using the curated split in `fewshot_reference_test_split.json`.

- References per action: 2
- Tests per category: 4
- Selection policy: For each (action, category), rank samples by annotation difficulty, template fit, and mirror margin, and pick 4 tests per category plus 2 non-overlapping references from the easiest/stablest categories.

## Layout

- `all_samples.csv`: all selected records with keypoint labels and copied image paths
- `vgm_examples.csv`: VGM-ready manifest; each row is one `(reference, test, point_id)` example
- `<action_slug>/references`: 2 curated reference images for that action
- `<action_slug>/tests`: 20 curated test images for that action
- `<action_slug>/references.csv` and `<action_slug>/tests.csv`: labels for the copied images after left-to-right canonicalization
- `<action_slug>/reference_overlays`: one overlay per reference image with all action keypoints drawn in consistent colors
- `<action_slug>/test_overlays`: one overlay per test image with the same point-color mapping
- `<action_slug>/vgm_examples.csv`: metadata linking clean images, overlays, and coords
- `<action_slug>/caption.yaml`: action caption manifest with one caption entry per reference/test image

## Orientation

- Selected keypoint chain point in a consistent left-to-right direction across clean images, overlays, and CSV coordinates.

## Point Labeling GUI

Run the Tkinter point labeler from the dataset root:

```bash
python3 tools/point_labeler_gui.py --action Hooking --points 4
```

The GUI uses Python `tkinter` and Pillow. Place new action images in `<action_slug>/references` and `<action_slug>/tests`, set the action's point count in the GUI when it is not 5, then mark the corresponding points on the reference/test pair. Add image captions in the reference/test caption boxes. `Save Pair` updates the action-level `references.csv`, `tests.csv`, overlays, `vgm_examples.csv`, and `caption.yaml`; `Save Captions` updates only `caption.yaml` and does not require all points to be marked. CSV point columns are written as `p1_x,p1_y,...,pN_x,pN_y`.

## Actions

- `Brush/Dust` -> `Brush_Dust`
- `Dagging` -> `Dagging`
- `Flip` -> `Flip`
- `Hooking` -> `Hooking`
- `Lift Something` -> `Lift_Something`
- `Mash/Pound` -> `Mash_Pound`
- `Mix` -> `Mix`
- `Poke` -> `Poke`
- `Pour` -> `Pour`
- `Pull out a nail` -> `Pull_out_a_nail`
- `Scoop` -> `Scoop`
- `Scrape` -> `Scrape`
