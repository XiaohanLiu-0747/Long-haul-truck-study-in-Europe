# Solar and Storage Integration for Electric Truck Charging

This repository provides a computational workflow for assessing photovoltaic (PV) and battery storage integration at electric truck charging stations. It calculates baseline electricity costs and levelized cost of charging (LCOC), optimizes PV and storage capacities and dispatch, and calculates cost components, PV utilization and discounted payback.

The supplied dataset contains 500 stations for one PV/storage scenario. A two-station demonstration is selected from the first two data rows of the station workbook. The workflow can process any number of leading rows from 1 to 500 without manually editing the input files.

## 1. System requirements

### Software dependencies and tested versions

The successful two-station end-to-end run used the following author-confirmed environment:

| Component | Tested version or status |
|---|---|
| Operating system | Windows, 64-bit; exact edition/build for the reference run remains to be confirmed |
| Python | 3.11.11, conda-forge, 64-bit (AMD64), in the Spyder runtime environment |
| NumPy | 2.2.4 |
| pandas | 2.2.3 |
| openpyxl | 3.1.5 |
| gurobipy | 12.0.2 |
| Gurobi Optimizer | 12.0.2 |
| Gurobi license | An academic license was used for the reference run. Users must configure their own valid license suitable for the model size. |

The two-station run completed all five computational stages and generated the reference results below. These Python and package versions were confirmed from the author's Spyder console.

Separately, the 500-station input checks and baseline calculations were tested on Windows 11 build 26200 with Python 3.12.14, NumPy 2.3.5, pandas 3.0.1 and openpyxl 3.1.5. That separate validation environment did not include Gurobi. 
macOS and Linux have not been tested for this release. A working Gurobi installation and a license suitable for the full model size are required. Installing `gurobipy` does not itself establish that a suitable license is available.

### Hardware requirements

No GPU or other specialized hardware is required. The code runs on a conventional CPU-based desktop computer. The author-reported reference computer has a 13th Gen Intel Core i5-1345U processor (1.60 GHz), 16.0 GB installed RAM (15.7 GB usable), and a 64-bit operating system on an x64-based processor. Minimum RAM and processor requirements have not been benchmarked; the optimization model must fit in available memory. Stations are processed sequentially, and each run stores separate input copies, dispatch CSVs and results, so sufficient free disk space is needed.

## 2. Installation guide

1. Download and extract the repository, preserving its folder structure.
2. Open a terminal or Anaconda Prompt in the project folder.
3. Create and activate a Python environment, then install the dependencies:

```text
python -m venv .venv
```

On Windows Command Prompt or Anaconda Prompt:

```text
.venv\Scripts\activate.bat
python -m pip install -r requirements.txt
```

The required third-party packages are `numpy`, `pandas`, `openpyxl` and `gurobipy`. The current `requirements.txt` does not pin versions. To install the package versions used in the successful reference run, use Python 3.11.11 and run:

```text
python -m pip install numpy==2.2.4 pandas==2.2.3 openpyxl==3.1.5 gurobipy==12.0.2
```

Matching package versions does not guarantee identical time-limited optimization solutions on different hardware.

4. Configure your Gurobi license according to the instructions supplied with your license.
5. Check the selected demo inputs without starting optimization:

```text
python run_pipeline.py 2 --validate-only
```

This command validates the selected station data, tariff tables, hourly load profiles and PV records. It does not run Gurobi or produce scientific results.

### Typical installation time

Allow approximately 5–15 minutes for environment creation and dependency installation on a normal desktop with a working internet connection. This is a planning estimate, not a measured installation benchmark. Download speed and package availability affect installation time. Obtaining or configuring a Gurobi license is excluded and may take longer.

## 3. Demo

### Included demonstration dataset

The first two data rows of the supplied station workbook correspond to `stop_id` 0 and 1. The demonstration automatically extracts these rows, their hourly load profiles and the associated PV records. The two stations use 576 PV records in total: 12 months × 24 hours × 2 stations.

Required input files are:

```text
zone_stop_info_merged_with_pv_area_pv_area_randomized_with_costs_with_LCOE.xlsx
electricity price.xlsx
power price.xlsx
network fee.xlsx
weather_per_stop_filtered_by_id_split_time_hour_plus2_diff3600_grp24_sorted_pvlib_PEREZ.csv
PV_simulation/<stop_id>/hour_year15_template.xlsx
```

### Instructions to run the demo

With the Python environment activated, run:

```text
python run_pipeline.py 2
```

The number `2` means the first two data rows in the original Excel workbook order, excluding its header. Station identifiers are not sorted or renumbered. Providing the count explicitly also overrides any locally edited default value.

The entry point automatically executes:

1. Baseline electricity-cost and LCOC calculation, including network-fee sensitivity.
2. PV/storage capacity and dispatch optimization.
3. Optimized cost-component and LCOC calculation.
4. PV-utilization and discounted-payback calculation.
5. Current-scenario comparison against baseline and consolidated output generation.

### Expected output

Each invocation creates a separate folder:

```text
runs/first_2_<timestamp>_<unique-id>/
```

The final consolidated result is:

```text
results/final_station_results.xlsx
```

This path is relative to the new run folder. The final workbook contains one row per selected station and includes station ID, country, baseline and optimized LCOC, relative LCOC reduction, optimized PV/storage capacities, cost components, PV utilization, payback and optimization status.

The successfully completed reference two-station run produced the following rounded values:

| Metric | Station 0 | Station 1 |
|---|---:|---:|
| Baseline LCOC (EUR/kWh) | 0.28532242 | 0.27858121 |
| Optimized LCOC (EUR/kWh) | 0.28151509 | 0.27857691 |
| LCOC reduction (%) | 1.33439448 | 0.00154353 |
| PV capacity (kW) | 596.9470 | 49.0796 |
| Storage capacity (kWh) | 2.6255 | 0 |
| PV utilization (%) | 97.1378 | 0 |
| Discounted payback (years) | 3 | `no` |
| Optimization status | `solved` | `solved` |

`no` denotes no payback within the 15-year evaluation horizon; the implementation also uses it when initial PV/storage capital expenditure is nonpositive. PV utilization is defined as PV energy supplied to EV charging plus PV energy supplied to storage, divided by total PV generation over the evaluation horizon. It excludes exported PV energy. A station can therefore have nonzero PV capacity and zero PV utilization if generation is exported.

`gap_LCOE` is stored as a fraction, not a percentage. It is calculated as `(baseline LCOC - scenario LCOC) / baseline LCOC`.

The reference values are example results, not assertions of a unique optimum. Gurobi uses a 1% relative MIP-gap target and a 100-second optimization time limit per station. `solved` means a feasible solution was obtained; it does not by itself establish that the target gap was reached. Solver gaps and statuses are recorded in `results/current_scenario/Optimization_results/mip_gap_summary.xlsx`. Results may vary with solver version, hardware and time-limited incumbent solutions.

Other outputs include:

- `results/baseline.xlsx`: recalculated baseline costs for the selected stations.
- `results/network_fee_sensitivity_results.xlsx`: selected stations × the 115 supplied network-fee pairs; 230 rows for the two-station demo.
- `results/current_scenario/optimized.xlsx`: optimized capacities and station statuses.
- `results/current_scenario/Optimization_results/<stop_id>/`: dispatch flows and metadata.
- `results/current_scenario/costs.xlsx`: optimized cost decomposition.
- `results/current_scenario/pv_utilization_payback_point_table.xlsx`: utilization and payback.
- `results/scenario_lcoc_comparison.xlsx`: scenario-versus-baseline comparison.
- `selected_stations.csv`, `run_manifest.json` and `logs/`: selected IDs, run status and stage logs.

Existing result columns in the copied input workbook are not evidence of results from the new run. Use `final_station_results.xlsx` and confirm that `run_manifest.json` reports `completed`.

### Expected demo runtime

The two-station demonstration completed in approximately **30 seconds**, as reported by the author for the successful reference run. This is an approximate observed runtime, not a guarantee for other computers. The reference computer has an Intel Core i5-1345U processor and 16.0 GB RAM. The configured solver time allowance is approximately 200 seconds for two stations if both reach their 100-second limit; model construction, input/output and postprocessing add overhead. Actual runtime depends on hardware, solver version and the solutions found.

## 4. Instructions for use

### Run additional supplied stations

To run the first 10 stations:

```text
python run_pipeline.py 10
```

To run all 500 supplied stations:

```text
python run_pipeline.py 500
```

The program rejects counts outside the available row range. All stages use the same selected station IDs. A failed stage stops the workflow and records the error rather than continuing with previous results. Source inputs and earlier runs are retained.

### Run the software on your own data

Prepare a separate input folder using the same filenames and schemas as the supplied data. Run:

```text
python run_pipeline.py 2 --data-dir "path/to/your_data"
```

Replace `2` with the number of leading station rows to process. Required input conventions are:

| Input | Required structure |
|---|---|
| Station workbook | One row per station, with unique integer `stop_id`; `Country`, `Latitude`, `CCS_num`, `MCS_num`, `stop_demand_total`, `overhead_cost`, `PV_area1`, `PV_area2`, `PV_install`, `PV_OM`, `storage_install`, `storage_OM`, `LCOE`; and `CCS_demand_year1` through `CCS_demand_year15` plus corresponding `MCS_demand_year*` columns |
| Demand cells | Text representations of 24-value numeric lists, in the same units and hourly order as the supplied workbook |
| PV identifiers | A nonmissing `id` is used for PV matching; otherwise `id_num` is used. These values match `stop_id` in the PV CSV. Load folders instead use the station workbook's `stop_id` |
| Electricity and network-share tables | `GEO (Labels)` and `level 1` through `level 7`, including an `average` row |
| Network-fee table | Numeric `energy fee` and `power fee` columns, in EUR/kWh and EUR/kW/month respectively |
| PV CSV | Semicolon-separated, with `stop_id`, `month`, `hour`, `PV_power_kW`; exactly one record per selected PV ID, month 1–12 and hour 0–23 |
| Hourly load workbook | `PV_simulation/<stop_id>/hour_year15_template.xlsx`; 24 unique hours numbered 1–24 and columns `year1` through `year15` |
| Load-profile cells | Power-duration pairs such as `[100,30; 0,30]`, with power in kW and duration in minutes; durations sum to 60 minutes per hourly cell |

Keep the supplied physical units and economic definitions. The optimizer interprets PV power using its original 0.327-kW module normalization; an arbitrary whole-system PV generation series is not interchangeable with that input. PV areas are in square metres and latitude is in degrees. `stop_demand_total` is the supplied baseline LCOC denominator and must be prepared consistently with the original scientific method; the program does not infer or reconstruct it for new datasets.

Run `--validate-only` first. These checks establish input compatibility, not the scientific suitability of a new dataset or cost assumptions.

### Reproduction scope

This release demonstrates one supplied scenario for 500 stations. It does not include the additional PV-siting/storage-cost scenario tables needed to reproduce a nine-scenario analysis, nor the full set of manuscript figure-generation scripts. It should not be described as reproducing every quantitative result in the manuscript.

The implementation preserves the original discount rate (0.095), 15-year evaluation horizon, 25/15-year PV/storage capital recovery factors, PV degradation, tariff thresholds and optimization equations. Baseline uses the original charger-cap-limited annual peak and supplied demand denominator; optimized cost/payback calculations retain the original raw-profile monthly-peak convention. These conventions are not silently harmonized by the entry point.

## 5. Source-code organization

| File | Purpose |
|---|---|
| `run_pipeline.py` | Single entry point; selects the first N stations and runs all stages |
| `pipeline_io.py` | Shared relative paths and input checks |
| `01_calculate_baseline.py` | Baseline electricity costs and LCOC |
| `02_optimize_pv_storage.py` | PV/storage sizing and dispatch optimization |
| `03_calculate_pv_storage_costs.py` | Optimized costs and LCOC |
| `04_calculate_pv_utilization_payback.py` | PV utilization and discounted payback |
| `05_compile_scenario_results.py` | Current-scenario comparison against baseline |
| `requirements.txt` | Python dependency list |

Keep all seven Python files together. The reviewer only needs to invoke `run_pipeline.py`.

## 6. License and repository

The software is released under the **MIT License**. See the accompanying `LICENSE` file. Gurobi is a third-party dependency with separate license terms; the project license does not grant a Gurobi license.

**Public repository URL: TO BE ADDED after upload.**

## Information to complete before submission

- Confirm the operating-system version used for the end-to-end run. The author has supplied the CPU (Intel Core i5-1345U), installed RAM (16.0 GB), 64-bit system architecture and approximate two-station runtime (30 seconds).
- Replace estimated installation time with a measured typical value if available.
- Add the public repository URL after upload. The MIT source-code license has been confirmed by the author.
