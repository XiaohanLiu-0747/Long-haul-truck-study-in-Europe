"""Compare the one supplied PV/storage scenario with baseline by station ID."""
import argparse
from pathlib import Path
import pandas as pd
from pipeline_io import MAIN_NAME, station_key


def keyed(frame, label):
    frame = frame.copy()
    frame['stop_id'] = frame['stop_id'].map(station_key)
    if frame.stop_id.duplicated().any():
        raise ValueError(f'{label}: duplicate stop_id')
    return frame.set_index('stop_id')


def compile_results(root, use_supplied_results=False):
    results = root / 'results'
    master = keyed(pd.read_excel(results / 'baseline.xlsx'), 'baseline')
    path = root / MAIN_NAME if use_supplied_results else results / 'current_scenario/costs.xlsx'
    frame = keyed(pd.read_excel(path), 'current scenario')
    if set(frame.index) != set(master.index):
        raise ValueError('Current scenario station IDs differ from baseline')
    baseline = pd.to_numeric(master['total_cost_baseline'], errors='raise')
    series = pd.to_numeric(frame['LCOC_new'], errors='raise').reindex(master.index)
    if not use_supplied_results:
        if 'optimization_status' not in frame:
            raise ValueError('Missing optimization_status; run stages 02 and 03 first')
        if not frame.optimization_status.isin(['solved', 'no_pv_area']).all():
            raise ValueError('Failed or uncomputed stations must be resolved before compilation')
        if series[frame.optimization_status.reindex(master.index) == 'solved'].isna().any():
            raise ValueError('Solved stations have missing LCOC')
    # Retain the original base-scenario rule for blank scenario values.
    filled = series.isna()
    series = series.fillna(baseline)
    output = pd.DataFrame({'total_cost_baseline': baseline, 'total_cost_LCOE': series,
                           'gap_LCOE': (baseline-series)/baseline.where(baseline != 0),
                           'filled_from_baseline': filled,
                           'scenario_source': 'supplied workbook; not recomputed' if use_supplied_results else 'revised pipeline'})
    target = results / ('supplied_scenario_comparison.xlsx' if use_supplied_results else 'scenario_lcoc_comparison.xlsx')
    output.reset_index().to_excel(target, index=False)
    print(f'Compared {len(output)} stations for the one supplied scenario: {target.name}')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--use-supplied-results', action='store_true',
                        help='Compare existing LCOC_new values in the supplied workbook; no optimization is rerun.')
    args = parser.parse_args()
    compile_results(args.data_dir.resolve(), args.use_supplied_results)
