# User Guide — Torque & Drag ML Calibration

Part A is for users (engineers), part B for the server operator.

> An interactive version of this guide is in the application: menu **How-to Guide** (Quick Start,
> step by step, use cases, system flow diagrams, outputs, FAQ, with search). For first-time users:
> **How-to Guide → Tutorial → "Tutorial: test the model on a well"**.

## What This System Does

*A brief overview of the system, the data used, and the workflow from historical data to Torque &
Drag predicting.*

Torque & Drag (T&D) models and actual field measurements are prepared and recorded by the
Directional Driller (DD) during drilling operations. The dataset includes modeled and actual
hookload under pick-up, slack-off, and rotating conditions, as well as torque, referenced against
measured depth.

The Machine Learning (ML) system learns the relationship and patterns between historical T&D model
outputs and actual field measurements from previously drilled wells. Based on these learned
patterns, the system generates a forward-looking prediction of Torque & Drag behavior at upcoming
drilling depths.

## Workflow

```
1. Training Data: upload historical wells (select section + type)  ->  2. Data Quality: review status C
3. Models: Freeze dataset + Train model, read the report, blind test
4. Monitoring: upload the well being drilled (select section + type)
5. Dashboard: charts, Prediction N ft ahead with cause and effect, operating limits
6. Output: Excel / PDF / Prediction (.xlsx)  ->  7. Evaluations: prediction vs actual after drilling
```

**Training Data and Monitoring are never mixed.** Only Training Data teaches the ML model.
Monitoring wells are predicted and evaluated only, even when they contain actual readings.

---

## A. User guide

### 1. Sign in
Open the application address (laptop: http://localhost:8401). Enter the admin username and
password. The session lasts 8 hours. After 5 wrong passwords, sign-in is locked for 15 minutes. The
eye icon in the password field shows/hides the password.

### 2. Preparing well files
One Excel file = one well section. Two original formats and the template are accepted:

| Format | Recognised by | T&D model (WellPlan) | Actual data |
|---|---|---|---|
| **A. T&D roadmap** (`.xlsx`) | sheets `Drag`, `Torque`, `T&D Actual Reading` | blocks per OHFF (e.g. 0.1/0.3/0.5 or 0.3/0.4/0.5) + DD **Calibrate** offsets | `T&D Actual Reading` (Klbs, Lbs-ft) |
| **B. WellPlan report** (`.xlsm`) | sheets `Summary`, `Tripping Load Analysis`, … | OHFF 0.2–0.5 every 100 ft, torque on bottom from `Rotary Drill Buckling Outputs`, survey, BHA, mud weight | `Drilling Data` (+ `Tripping  Data`) |
| **Template** (`.xlsx`) | downloaded from the application | same layout as A | `T&D Actual Reading` |

**DD Calibrate offsets** (format A and template): Drag row 1 labels `PICK UP / SLACK OFF / ROTATE`
with the values in row 2 (klbf); Torque `Calibrate On Bot Torque` in C2 and the off-bottom offset in
C3 (ft-lbf). The dashboard shows the T&D model with these offsets by default, exactly like the
Excel "Graph reference" crossplot.

### 3. Training Data
**a. Upload.** Select **Well section** and **Well type** (required), optionally download the
*Training data template*, fill it in (sheet *Instructions*), and drop the files. Several files at
once are fine when they share the section and type. The result shows the import status and the
data quality (A/B/C) per file. A/B wells are used in the next training run.

**b. Bulk import from folder** (administrator, many historical wells). Folder layout as the client's
`Training` folder:
```
data/inbox/
  Horizontal/                 <- well type (J, S, Horizontal)
    MINAS 2193 (2D-96A) HW/   <- folder name = well code
      P_MINA25_0017HW_BHA1A_17.5in_TnD.xlsm   <- well section read from the file name
```
Click **Scan folder**. Per file: `accepted`, `accepted with warnings`, `duplicate`, `skipped`
(modified < 1 minute ago), `rejected` + reason. Files move to `data/processed/` or `data/rejected/`
(with `.reason.txt`). The folder scan always imports as Training Data.

**c. Well list.** Filter by section, type and data quality, search by name, and group by section,
type, section × type or quality. The import history can be filtered by status.

### 4. Data Quality
| Status | Meaning | Used for training? |
|---|---|---|
| **A** Accepted | passed all checks | yes |
| **B** Accepted with warnings | passed the critical checks, statistical warnings | yes, flagged |
| **C** On hold | failed a critical check | no, waiting for review |
| **X** Excluded | excluded by an engineer's review | no |

**Critical checks:** core T&D model operations present, plausible units, no conflicting duplicate
depths, plausible values, order slack off ≤ rotating ≤ pick up, at least **8 actual pick-up points
within the T&D model depth range**, section & type known, not a duplicate of another well.
**Statistical warnings:** actual/T&D model ratio deviates from similar wells (MAD), implausible
jumps, repeated values, far fewer points than similar wells, torque ratio far from 1, decreasing
depth order in the file.

Click a well to see all checks and record a decision: **Accept** (C → B), **Exclude** (X), or
**Fix** (stays C, request a new file). A reason is required; the reviewer and time are recorded.
**Download quality report (.xlsx)** to send to the client.

### 5. Models
**a. Freeze a dataset.** All actual points of Training Data wells with status A/B, paired with the
T&D model at the same depth, plus features (depth, T&D model OHFF 0.3 & 0.5, OHFF slope, rotating
weight, section, type, file format and the extra feature groups). Freezing saves a snapshot + hash.
The first dataset also **locks ~20% of the wells as the blind test** (proportional per type).

**b. Train a model** (about 3–5 minutes):
1. Feature group tests (survey, casing shoe, BHA & mud, KOP & interval type, block weight,
   **DD Calibrate offset**): a group is used only if it lowers the error by ≥ 1%.
2. All candidates × direct/residual target, scored with **cross-validation grouped by well**.
3. Single model vs one model per section × type (if ≥ 10 wells).
4. Learning curve, error analysis, SHAP, uncertainty band (P10–P90).
5. Compared with the active model: **worse → held** (can be activated manually).

**c. Read the report**, **d. run the blind test once** per model.

### 6. Monitoring
Select **Well section** and **Well type**, optionally download the *Monitoring well template*,
upload one file (T&D model, plus actual readings so far if available). The system imports, checks
and predicts with the active model, and shows a summary per operation (T&D model OHFF 0.3, ML
prediction, P10–P90, ML − T&D model) with links to the dashboard, Excel and PDF. Upload the file again
as drilling progresses. After the well is finished, **Promote to training** copies it into Training
Data (it then goes through the data quality gate).

### 7. Dashboard
- Filters: **Data group**, **Well section**, **Well type**, **Quality**, **Well**, **Units**
  (imperial/SI), **Model**, **WellPlan curves** (Automatic / With DD Calibrate / As modelled).
- Panels stacked: Hookload, Torque, Difference (Δ). Y axis `Depth (ft)`.
- Standard series names: `PU - OHFF : 0.3`, `SO - OHFF : 0.5`, `ROT` (one curve),
  `Torque On Bottom - OHFF : 0.3`, `Torque Off Bottom - OHFF : 0.5`; ML `PU - ML`, actual
  `PU Actual`. PU and SO are told apart by name and position (as in the client's Excel); dashed
  lines are reserved for the uncertainty band.
- One fixed colour per OHFF in every chart (light → dark blue for 0.1 → 0.5); ML prediction orange;
  actual readings green points; **uncertainty band (P10–P90) dashed**; **operating limits dotted**
  red.
- Defaults: **All OHFF curves** on, **Uncertainty band (P10–P90)** off.
- Difference = A − B: right (+) = A is higher. Intervals with |Δ| above the threshold are shaded.
- Training wells show an **unseen-well validation** prediction (a model that never saw that well).

### 8. Prediction N ft ahead
Dashboard → **Prediction ahead**: enter the distance (e.g. 300 ft); the start is the last actual depth
(or the top of the T&D model). **Local bias correction** (median actual − ML of the last 10 actual
points within 1,000 ft; display only) is **on by default** when the well has actual readings.
The column **Expected accuracy** shows the backtest of the active model for that distance on wells
it never saw: share of points within the client tolerance (< 10 klbf hookload, < 2 kft-lbf torque). Output per operation: ML prediction, P10–P90 and the
T&D model per OHFF every 30 ft, plus **cause and effect**:
- main drivers (local SHAP contributions to the change over the window),
- plan changes (inclination, maximum dogleg, interval type),
- operating limits reached by the prediction or the band, with the depth,
- an automatic sentence, e.g. *"Pick up: from 8,450 to 8,750 ft the ML prediction is expected to rise
  from 210.3 to 225.1 klbf (+14.8). Main drivers: T&D Model (+10.2), Inclination (+3.1)…"*.

The window is shaded in the charts. **⬇ Prediction (.xlsx)** exports it (Summary, one sheet per
operation with a chart, Explanation). The prediction stops where the WellPlan results end.

### 8b. Accuracy against the client tolerance
Every model reports the share of actual points with |ML − actual| < 10 klbf (hookload) or < 2 kft-lbf
(torque): Models → report (main table, *Prediction backtest* tab for 300 / 600 / 1,000 ft), the model
report Excel/PDF, and the dashboard metrics of each well.

### 9. Operating limits
Add limits (e.g. pick up max, torque on bottom max = top drive limit, slack off min) for this well
or the whole section. The table shows the first depth where ML, the ML band bound and the T&D model
reach the limit, and the minimum margin.

### 10. Output
- **Export Excel** (per well, file `OUTPUT <well> <section>in Multiple T&D Road Map.xlsx`, same layout
  as the client's template):
  - `Summary Outputs`: "ML PREDICTION ANALYSIS SUMMARY REPORT", well info, table *ACTUAL VS Machine
    Learning* (Actual / ML / Actual − ML for PU, SO, ROT and torque), Drag and Torque prediction
    performance metrics (T&D model, T&D + DD Calibrate, ML; R2, RMSE, MAE, MAPE), parity charts.
  - `Tripping Load Analysis - Graph`: MODELLED HOOKLOADS (SO/PU per OHFF, RT off bottom), ACTUAL
    HOOKLOADS, TRIPPING DATA, plus ML PREDICTION (with P10/P90) and the drag chart.
  - `Torque Analysis Off Btm` / `On Bottom`: MODELLED TORQUE per OHFF, actual torque, ML prediction
    and chart (Kft.lbf).
  - `ROT / SO / PU MW <mud weight>`: WellPlan "Multipoint Torque and Drag Outputs" (header, BHA &
    wellbore data, drilling parameters, BHA and wellbore description, per-OHFF table), model as
    modelled. Surface torque while tripping is not in the source files and stays empty.
- **PDF**: data quality, model & dataset versions, metrics, operating limits, six chart panels.
- **Prediction (.xlsx)**, **model report (.xlsx / PDF)**, **data quality report (.xlsx)**.

### 11. Evaluations
When the actual data of a prediction monitoring well is uploaded later, the stored prediction is
compared with the actual data and with the T&D model automatically.

---

## B. Operations (Docker)

```bash
make up                       # start / update (migrations run automatically)
make logs                     # application log
make down                     # stop (data stays in the volumes)
make password                 # change the admin password + remove the sign-in lock
make inbox-training           # copy Training/ to data/inbox
make practice-files           # synthetic practice files -> data/practice/{training,monitoring}
make audit                    # file audit report -> data/audit/
make backup                   # manual database dump -> backups/
docker compose exec app python -m app.cli refresh-meta   # re-read DD Calibrate, BHA, wellbore
docker compose exec app python -m app.cli recompute-quality
docker compose exec db psql -U tdml -d tdml
```
**Never** run `docker compose down -v` on the server (deletes the database, uploads and models).

### Data folders
| Folder | Content | In Git? |
|---|---|---|
| `Training/` | the client's original well data | no |
| `data/inbox/` | files waiting to be scanned | no |
| `data/processed/`, `data/rejected/` | files after scanning | no |
| `data/practice/` | synthetic practice files | no |
| `data/audit/`, `data/reports/` | reports containing well names | no |
| volumes `uploads`, `models` | imported file copies, `.joblib` models, frozen datasets | no |

`data/` must be writable by uid 1000 (the user inside the container) and closed to other users:
`sudo chown -R 1000:1000 data && chmod 750 data`.

### Retraining when new data arrives
1. Upload in Training Data or scan the folder (or Promote a finished monitoring well).
2. Review status C in Data Quality.
3. Models → **Freeze a new dataset** (the existing blind test stays locked).
4. **Train model** with the new dataset. If it is worse than the active model, it is held.

### Upgrading to this version (feedback #1)
Migrations `0003` (Training/Monitoring) and `0004` (English status codes) run on `make up`.
Migration 0004 clears the stored data quality, so afterwards run:
```bash
docker compose exec app python -m app.cli refresh-meta
docker compose exec app python -m app.cli recompute-quality
```
Then freeze a new dataset and train (the DD Calibrate feature group is tested automatically).

### Backup and restore
- Service `backup`: daily dump in `./backups` (7 days).
- Also copy the `uploads` and `models` volumes:
  `docker run --rm -v td-ml_models:/m -v $PWD/backups:/b alpine tar czf /b/models.tgz -C /m .`
- Test a restore once before hand-over:
  ```bash
  docker compose exec -T db createdb -U tdml tdml_test
  gunzip -c backups/last/tdml-*.sql.gz | docker compose exec -T db psql -q -U tdml -d tdml_test
  docker compose exec -T db dropdb -U tdml tdml_test
  ```

### Hand-over
1. `make password` → new password, hand it over through a secure channel.
2. Make sure `.env` has no `ADMIN_PASSWORD`.
3. Test the full flow on the server: Training upload → Data Quality → Train → Blind test →
   Monitoring upload → Prediction → Excel/PDF.
4. Delete copies of client data on laptops within 14 days (Article 11(4)).
