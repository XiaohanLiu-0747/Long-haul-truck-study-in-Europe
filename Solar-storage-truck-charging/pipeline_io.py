"""Shared input validation and paths for the five computational stages."""
import argparse
import ast
from functools import lru_cache
from pathlib import Path
import numpy as np
import pandas as pd

MAIN_NAME = 'zone_stop_info_merged_with_pv_area_pv_area_randomized_with_costs_with_LCOE.xlsx'
PV_NAME = 'weather_per_stop_filtered_by_id_split_time_hour_plus2_diff3600_grp24_sorted_pvlib_PEREZ.csv'

def station_key(value):
    number = float(value)
    if not np.isfinite(number) or number != int(number):
        raise ValueError(f'Invalid station identifier: {value}')
    return str(int(number))

def pv_identifier(row):
    # Preserve the optimizer's original priority consistently in all stages.
    return int(station_key(row['id'] if pd.notna(row.get('id')) else row['id_num']))

@lru_cache(maxsize=512)
def read_template(path):
    frame = pd.read_excel(path)
    required = ['hour'] + [f'year{y}' for y in range(1, 16)]
    if set(required) - set(frame):
        raise ValueError(f'{path}: missing template columns')
    if len(frame) != 24 or set(frame.hour) != set(range(1, 25)):
        raise ValueError(f'{path}: expected unique hours 1 through 24')
    for col in required[1:]:
        for cell in frame[col]:
            pairs = [tuple(map(float, part.strip().split(','))) for part in str(cell).strip('[]').split(';')]
            if any(len(pair) != 2 or not np.isfinite(pair).all() or min(pair) < 0 for pair in pairs):
                raise ValueError(f'{path}: invalid load slice in {col}')
            if not np.isclose(sum(pair[1] for pair in pairs), 60):
                raise ValueError(f'{path}: slice durations must sum to 60 minutes')
    return frame

def read_flows(path):
    frame = pd.read_csv(path, sep=';')
    keys = ['year', 'month', 'hour', 'o']
    if set(keys + ['value']) - set(frame) or frame.empty:
        raise ValueError(f'{path}: missing or empty flow data')
    if frame.duplicated(keys).any() or not np.isfinite(frame[keys + ['value']].to_numpy()).all():
        raise ValueError(f'{path}: duplicate or nonfinite flow data')
    expected = {(y, m, h) for y in range(1, 16) for m in range(1, 13) for h in range(1, 25)}
    if set(map(tuple, frame[['year', 'month', 'hour']].to_numpy())) != expected:
        raise ValueError(f'{path}: incomplete year/month/hour coverage')
    return frame

def validate_station_table(frame, root):
    required = ['stop_id', 'Country', 'Latitude', 'CCS_num', 'MCS_num', 'stop_demand_total',
                'overhead_cost', 'PV_install', 'PV_OM', 'storage_install', 'storage_OM', 'LCOE', 'PV_area1', 'PV_area2']
    required += [f'{kind}_demand_year{y}' for kind in ('CCS', 'MCS') for y in range(1, 16)]
    missing = set(required) - set(frame)
    if missing:
        raise ValueError(f'Missing station columns: {sorted(missing)}')
    ids = frame.stop_id.map(station_key)
    if ids.duplicated().any():
        raise ValueError('Duplicate stop_id values')
    for _, row in frame.iterrows():
        for col in required:
            if '_demand_year' in col:
                values = np.asarray(ast.literal_eval(str(row[col])), dtype=float)
                # Retain tiny negative floating-point residuals from the supplied model.
                if values.shape != (24,) or not np.isfinite(values).all() or (values < -1e-8).any():
                    raise ValueError(f'Station {row.stop_id}: invalid {col}')
        read_template(root / 'PV_simulation' / station_key(row.stop_id) / 'hour_year15_template.xlsx')

def configure(stage):
    parser = argparse.ArgumentParser(description=f'Run {stage} for the supplied station table.')
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    root = args.data_dir.resolve()
    result = root / 'results'
    scenario_dir = result / 'current_scenario'
    baseline = result / 'baseline.xlsx'
    source = root / MAIN_NAME
    if stage == 'optimization':
        source = baseline
    elif stage in ('costs', 'payback'):
        source = scenario_dir / 'optimized.xlsx'
    required = [source, root / 'electricity price.xlsx', root / 'power price.xlsx', root / 'network fee.xlsx']
    if stage in ('optimization', 'costs', 'payback'):
        required.append(root / PV_NAME)
    missing = [str(p.relative_to(root)) for p in required if not p.is_file()]
    if missing:
        raise FileNotFoundError('Missing inputs: ' + ', '.join(missing))
    frame = pd.read_excel(source)
    validate_station_table(frame, root)
    for name in ('electricity price.xlsx', 'power price.xlsx'):
        tariff = pd.read_excel(root / name)
        if 'GEO (Labels)' not in tariff or not (tariff['GEO (Labels)'].astype(str).str.strip().str.lower() == 'average').any():
            raise ValueError(f'{name}: missing average tariff row')
        values = tariff[[f'level {i}' for i in range(1, 8)]].apply(pd.to_numeric, errors='raise')
        if not np.isfinite(values.to_numpy()).all():
            raise ValueError(f'{name}: nonfinite tariff')
    if stage in ('optimization', 'costs', 'payback'):
        pv = pd.read_csv(root / PV_NAME, sep=';')
        if set(['stop_id', 'month', 'hour', 'PV_power_kW']) - set(pv):
            raise ValueError('PV CSV requires stop_id, month, hour, PV_power_kW')
        for _, row in frame.iterrows():
            sub = pv[pv.stop_id == pv_identifier(row)]
            if len(sub) != 288 or sub.duplicated(['month', 'hour']).any() or set(zip(sub.month, sub.hour)) != {(m,h) for m in range(1,13) for h in range(24)}:
                raise ValueError(f'Station {row.stop_id}: PV CSV needs 12 months by hours 0..23')
            if not np.isfinite(sub.PV_power_kW).all() or (sub.PV_power_kW < 0).any():
                raise ValueError(f'Station {row.stop_id}: invalid PV power')
    if stage in ('costs', 'payback'):
        if 'optimization_status' not in frame:
            raise ValueError('Run the revised optimizer first; existing capacities have no solver provenance')
        for _, row in frame.iterrows():
            if row.get('optimization_status') != 'solved':
                continue
            caps = np.asarray([row.get('Capacity_PV_opt'), row.get('Capacity_storage_opt')], dtype=float)
            if not np.isfinite(caps).all() or (caps < 0).any():
                raise ValueError(f'Station {row.stop_id}: invalid optimized capacities')
            for name in ('S_PV_EV', 'S_ST_EV', 'S_PV_ST', 'S_grid_ST'):
                read_flows(scenario_dir / 'Optimization_results' / station_key(row.stop_id) / f'{name}.csv')
    print(f'Validated {len(frame)} stations for {stage}; current supplied scenario')
    if args.validate_only:
        raise SystemExit(0)
    scenario_dir.mkdir(parents=True, exist_ok=True)
    return root, source, result, scenario_dir
