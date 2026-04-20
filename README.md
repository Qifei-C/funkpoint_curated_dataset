# FunKPoint Curated Dataset

This dataset was materialized from `labels.csv` using the curated split in `fewshot_reference_test_split.json`.

- References per action: 2
- Tests per category: 4
- Selection policy: For each (action, category), keep only samples whose p1->p5 direction has |dx|/sqrt(dx^2+dy^2) >= 0.6; then choose the best left/right-consistent sign cluster under that filter, rank samples by annotation difficulty, template fit, and mirror margin, and pick 4 tests per category plus 2 non-overlapping references from the easiest/stablest categories.

## Layout

- `all_samples.csv`: all selected records with keypoint labels and copied image paths
- `vgm_examples.csv`: VGM-ready manifest; each row is one `(reference, test, point_id)` example
- `<action_slug>/references`: 2 curated reference images for that action
- `<action_slug>/tests`: 20 curated test images for that action
- `<action_slug>/references.csv` and `<action_slug>/tests.csv`: labels for the copied images after left-to-right canonicalization
- `<action_slug>/reference_overlays`: one overlay per reference image with all 5 points drawn in consistent colors
- `<action_slug>/test_overlays`: one overlay per test image with the same 5-color mapping
- `<action_slug>/vgm_examples.csv`: metadata linking clean images, overlays, and coords

## Orientation

- Selected samples are horizontally reflected when needed so `p1` lies to the left of `p5`.
- This makes the keypoint chain point in a consistent left-to-right direction across clean images, overlays, and CSV coordinates.

## Actions

- `Brush/Dust` -> `Brush_Dust`
- `Flip` -> `Flip`
- `Lift Something` -> `Lift_Something`
- `Mash/Pound` -> `Mash_Pound`
- `Mix` -> `Mix`
- `Poke` -> `Poke`
- `Pour` -> `Pour`
- `Pull out a nail` -> `Pull_out_a_nail`
- `Scoop` -> `Scoop`
- `Scrape` -> `Scrape`
