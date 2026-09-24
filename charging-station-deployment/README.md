# Charging Station Deployment for Electric Long-Haul Trucks

This repository provides a MATLAB workflow for regional charging-station deployment, annual charging-demand allocation and levelized cost of charging (LCOC) calculation. The workflow determines CCS and MCS charger numbers, allocates demand over a 15-year evaluation horizon and produces consolidated station results.

The supplied dataset contains 10 regions, 116 unique candidate stations and 86 node CSV files containing 3,993 records. Users can select the first N regions in numeric folder order. The count refers to regions, not individual stations.

## 1. System requirements

### Software dependencies and tested versions

| Component | Version or status |
|---|---|
| Operating system | Windows, 64-bit; exact edition/build used for the supplied result remains to be confirmed |
| MATLAB | Required. R2023b Code Analyzer was used for static checks; the release used for the author's optimization run remains to be confirmed |
| YALMIP | 20230622, confirmed by the author using `yalmip('version')` |
| Gurobi Optimizer and MATLAB interface | 12.0.2, confirmed by the author for this workflow |
| Licenses | Working MATLAB and Gurobi licenses suitable for the model size are required. Academic users may use an eligible academic Gurobi license under its terms |

The author supplied a 10-region station result containing 116 rows, 69 CCS chargers and 59 MCS chargers. These output values were inspected. The author confirmed YALMIP 20230622, Gurobi 12.0.2 and an approximate elapsed runtime of two minutes for all 10 regions. The output values do not establish optimality gaps. The Python `gurobipy` package does not replace the Gurobi MATLAB interface.

macOS and Linux have not been tested for this release. Static checks and input checks have been performed; a fresh end-to-end run of this packaged version has not been independently verified.

### Hardware requirements

No GPU or specialized hardware is required. The author confirmed that this workflow used a computer with a 13th Gen Intel Core i5-1345U processor (1.60 GHz), 16.0 GB installed RAM and a 64-bit x64 operating system. Minimum CPU and RAM requirements have not been benchmarked. Models must fit in available memory, and free disk space is needed for separate run folders and checkpoints.

## 2. Installation guide

1. Extract the complete package, preserving its folder structure.
2. Install and activate MATLAB.
3. Install YALMIP and add its installation directory and subdirectories to the MATLAB path.
4. Install Gurobi with its MATLAB interface. Run `gurobi_setup` from the Gurobi MATLAB directory and configure a valid license.
5. Set MATLAB's Current Folder to the extracted project folder containing `run_deployment.m`.
6. In the MATLAB Command Window, check that the interfaces are available:

```matlab
which sdpvar
which optimize
which gurobi
```

Each command should identify its corresponding installed function. Then validate the supplied data without running optimization:

```matlab
run_deployment(10, true)
```

This checks data compatibility and writes input-validation outputs. It does not calculate deployment results or test solver-license availability.

### Typical installation time

Installation time has not been measured. If MATLAB and the solver are already installed and licensed, allow approximately 10–20 minutes to extract the package, configure paths and check dependencies. This is a planning estimate, not a benchmark. Full MATLAB/Gurobi downloads and license acquisition are excluded.

## 3. Demo

### Included demonstration dataset

The demo uses region `1`, which contains four candidate stations: `17614`, `17615`, `190339` and `190342`. All input files are included:

```text
matlab20250310.mat
opt_model_para_table/1/node_set.xlsx
opt_model_para_table/1/node_set_with_stop.xlsx
opt_model_para_table/1/zone_stop_info.xlsx
opt_model_para_table/1/<node_id>.csv
```

### Instructions to run the demo

Enter the following in the MATLAB Command Window:

```matlab
run_deployment(1)
```

The entry point automatically performs:

1. Input loading and zero initialization of charger counts and demand arrays.
2. Regional charger-capacity optimization using year-5 demand.
3. Annual demand allocation for years 1–15.
4. Cost and LCOC calculation and consolidated result export.

### Expected output

Each invocation creates a separate folder:

```text
results/run_<timestamp>_<unique-token>/
```

The main output files are:

| Output | Contents |
|---|---|
| `zone_stop_info_merged.xlsx` | One row per selected candidate station, charger numbers, 15 years of 24-hour demand profiles, costs and LCOC |
| `station_results.csv` | The same final station table, separated by semicolons |
| `solver_status.csv` | Regional/year solver status, objective and constraint residual |
| `run_status.mat` | Run completion or failure status |
| `selected_regions.csv`, `selected_stations.xlsx` | Selected region and station metadata |
| `initial_state.mat`, `deployment_state.mat`, `checkpoint.mat` | Initial arrays and intermediate calculation state |
| `run.log` | Execution log |

The one-region demo should produce four station rows, including stations assigned zero chargers. Zero-demand LCOC is undefined and is represented as NaN or blank. Check that `run_status.mat` reports `completed` before treating outputs as a completed run.

As a separate reference, the author-supplied 10-region output contained 116 candidate stations, 35 stations with chargers, 69 CCS chargers and 59 MCS chargers. These are observed reference values, not assertions of a unique optimum or expected values for the one-region demo. Multiple optima, time limits, solver settings and region selection can affect the resulting station allocation.

### Expected demo runtime

The author reports approximately **2 minutes for all 10 supplied regions** on the Intel Core i5-1345U computer with 16.0 GB RAM described above, using YALMIP 20230622 and Gurobi 12.0.2. This is an approximate observed runtime, not a guarantee for other computers. A separate one-region demo runtime has not been measured; it should not be inferred by dividing the 10-region runtime by ten.

The one-region demo solves one deployment model and 15 annual allocation models. All 10 regions require 10 deployment solves and 150 annual allocation solves. Each model has a 1,000-second time limit. Actual runtime depends on model size, hardware, solver version and the solutions found.

## 4. Instructions for use

### Run additional supplied regions

```matlab
run_deployment(2)   % First two regions in numeric folder order.
run_deployment(10)  % All ten supplied regions.
run_deployment      % All available numbered regions.
```

Every invocation starts from zero and creates a separate result folder. Earlier results are not used as initial capacities or demand. Within a run, regions are processed sequentially and share station state through station IDs. Repeated runs do not accumulate earlier results.

### Run the software on your own data

Use a separate copy of the project and prepare numbered regional folders under `opt_model_para_table`. All paths are relative to the program folder.

| Input | Required structure |
|---|---|
| `node_set.xlsx` | `node_id` values identifying the node CSV files |
| `node_set_with_stop.xlsx` | `node_id` and `stop`, with candidate station IDs encoded as numeric vectors |
| `zone_stop_info.xlsx` | `stop_id`, `Country`, `Latitude`, `Longitude`, `Area`, `LaborCostAdjust` |
| `<node_id>.csv` | `Selected_Nodes`, `charging_demand_m`, `charging_demand_n`, `ChargingAdjustmentFactors`, `Stop` |
| Demand profiles | Each demand vector contains 24 numeric values; each adjustment-factor vector contains 15 values |
| `matlab20250310.mat` | Required economic parameters, country labels and seven-column electricity tariff matrix |

Use unique integer station IDs within each regional station table. Shared station IDs must have consistent metadata across regions. Retain the supplied units, hourly ordering and demand definitions. Positive demand must have eligible candidate stations. The cost-input table is assembled from regional metadata and newly calculated results; a separate input `zone_stop_info_merged.xlsx` is not required.

The MAT file supplies hardware, installation and maintenance costs, charger area, charging loss, discount rate, labor-cost share, lifetime and electricity tariffs. The evaluation horizon is 15 years, with a 0.095 discount rate and year-5 deployment sizing. Reported construction costs exclude the station-selection penalty used in the optimization objective. Electricity tariff upper bounds are 20,000; 499,000; 1,999,000; 19,999,000; 69,999,000; 149,999,000; and infinity. Demand is assigned to the first inclusive upper bound that contains it.

Validate the inputs before optimization. Optional validation and cost checks are available through:

```matlab
test_deployment(false)
```

### Reproduction scope

Because this demonstration includes only 10 regions rather than the 856 regions configured in the full-study workflow, cross-region demand at shared boundary stations may differ, leading to different charger allocations at individual stations. Comparisons require the same region selection, demand inputs and economic assumptions.

## 5. Source-code organization

| File | Purpose |
|---|---|
| `run_deployment.m` | Single entry point selecting regions and executing all stages |
| `optimize_deployment.m` | Charger-capacity optimization |
| `assign_charging_demand.m` | Annual charging-demand allocation |
| `calculate_station_costs.m` | Costs and LCOC |
| `load_zone_data.m` | Regional input loading and demand/eligibility construction |
| `load_parameters.m` | Economic parameter and tariff loading |
| `parse_numeric_vector.m` | Numerical profile parsing |
| `verify_solution.m` | Solver status and feasibility checks |
| `test_deployment.m` | Input, initialization and cost tests |

Keep these files together. The reviewer only needs to invoke `run_deployment` for the computational workflow.

## 6. License and repository

The source code is released under the MIT License. See `LICENSE`. MATLAB, Gurobi and YALMIP have their own license terms; the project license does not grant licenses for those dependencies.

**Public repository URL: TO BE ADDED after upload.**

## Information to complete before submission

- Record the operating-system edition/build and MATLAB release used for the reference run. YALMIP 20230622 and Gurobi 12.0.2 have been confirmed.
- Record a separate one-region demo runtime if available. The author confirmed approximately two minutes for all 10 regions on an Intel Core i5-1345U computer with 16.0 GB RAM.
- Replace the installation-time estimate with an observed value if available.
- Add the public repository URL after upload.
