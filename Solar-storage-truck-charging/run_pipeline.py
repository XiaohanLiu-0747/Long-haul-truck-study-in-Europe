"""Run the complete scientific workflow for the first N workbook stations."""
import argparse
import csv
from datetime import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

import pandas as pd
from pipeline_io import MAIN_NAME, PV_NAME, pv_identifier, station_key

STAGES = (
    '01_calculate_baseline.py',
    '02_optimize_pv_storage.py',
    '03_calculate_pv_storage_costs.py',
    '04_calculate_pv_utilization_payback.py',
    '05_compile_scenario_results.py',
)


def select_stations(frame, count):
    if not 1 <= count <= len(frame):
        raise ValueError(f'Enter an integer from 1 to {len(frame)}; received {count}.')
    ids = frame['stop_id'].map(station_key)
    if ids.duplicated().any():
        raise ValueError('The source workbook contains duplicate stop_id values.')
    # iloc preserves the workbook row order; identifiers are not sorted or renumbered.
    return frame.iloc[:count].copy()


def prepare_inputs(source, destination, selected):
    selected.to_excel(destination / MAIN_NAME, index=False)
    for name in ('electricity price.xlsx', 'power price.xlsx', 'network fee.xlsx'):
        shutil.copy2(source / name, destination / name)
    for value in selected.stop_id:
        relative = Path('PV_simulation') / station_key(value) / 'hour_year15_template.xlsx'
        (destination / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / relative, destination / relative)
    pv_ids = {pv_identifier(row) for _, row in selected.iterrows()}
    coverage = {value: set() for value in pv_ids}
    retained = 0
    digest = hashlib.sha256()
    with (source / PV_NAME).open('rb') as incoming, (destination / PV_NAME).open('wb') as outgoing:
        header = incoming.readline()
        columns = next(csv.reader([header.decode('utf-8-sig')], delimiter=';'))
        position = {name: columns.index(name) for name in ('stop_id', 'month', 'hour', 'PV_power_kW')}
        outgoing.write(header)
        for line_number, line in enumerate(incoming, 2):
            row = next(csv.reader([line.decode('utf-8')], delimiter=';'))
            if len(row) != len(columns):
                raise ValueError(f'CSV row {line_number}: wrong number of columns.')
            pv_id = int(station_key(row[position['stop_id']]))
            if pv_id not in pv_ids:
                continue
            month = int(station_key(row[position['month']]))
            hour = int(station_key(row[position['hour']]))
            power = float(row[position['PV_power_kW']])
            if not (1 <= month <= 12 and 0 <= hour <= 23 and 0 <= power < float('inf')):
                raise ValueError(f'CSV row {line_number}: invalid month, hour or PV power.')
            key = (month, hour)
            if key in coverage[pv_id]:
                raise ValueError(f'PV station {pv_id}: duplicate month/hour {key}.')
            coverage[pv_id].add(key)
            outgoing.write(line)
            digest.update(line)
            retained += 1
    expected = {(month, hour) for month in range(1, 13) for hour in range(24)}
    if any(keys != expected for keys in coverage.values()):
        raise ValueError('Selected stations have missing PV month/hour records.')
    audit = pd.DataFrame({
        'source_excel_row': range(2, len(selected) + 2),
        'stop_id': selected.stop_id.to_numpy(),
        'pv_station_id': [pv_identifier(row) for _, row in selected.iterrows()],
    })
    audit.to_csv(destination / 'selected_stations.csv', index=False)
    return {'pv_rows': retained, 'pv_rows_sha256': digest.hexdigest(),
            'stop_ids_in_workbook_order': [station_key(value) for value in selected.stop_id]}


def run_stage(script, run_dir, validate_only=False):
    command = [sys.executable, '-u', str(run_dir / 'code' / script), '--data-dir', str(run_dir)]
    if validate_only:
        command.append('--validate-only')
    log = run_dir / 'logs' / (Path(script).stem + '.log')
    with log.open('w', encoding='utf-8') as stream:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   text=True, encoding='utf-8', errors='replace',
                                   env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
        try:
            for line in process.stdout:
                print(line, end='', flush=True)
                stream.write(line)
            return_code = process.wait()
        except BaseException:
            process.terminate()
            process.wait()
            raise
    if return_code:
        raise RuntimeError(f'{script} failed with exit code {return_code}. See {log}')


def final_summary(run_dir, selected):
    results = run_dir / 'results'
    sources = [
        (results / 'scenario_lcoc_comparison.xlsx',
         ['total_cost_baseline', 'total_cost_LCOE', 'gap_LCOE', 'filled_from_baseline']),
        (results / 'current_scenario/optimized.xlsx',
         ['Capacity_PV_opt', 'Capacity_storage_opt', 'optimization_status']),
        (results / 'current_scenario/costs.xlsx',
         ['LCOC_PV', 'LCOC_ST', 'LCOC_E', 'network cost new', 'energy cost new', 'power cost new']),
        (results / 'current_scenario/pv_utilization_payback_point_table.xlsx',
         ['PV utilization rate', 'payback']),
    ]
    summary = selected[['stop_id', 'Country']].copy()
    summary['stop_id'] = summary.stop_id.map(station_key)
    for path, columns in sources:
        frame = pd.read_excel(path)
        frame['stop_id'] = frame.stop_id.map(station_key)
        if frame.stop_id.duplicated().any() or set(frame.stop_id) != set(summary.stop_id):
            raise ValueError(f'{path.name}: output station IDs do not match the selected stations.')
        summary = summary.merge(frame[['stop_id'] + columns], on='stop_id', how='left',
                                sort=False, validate='one_to_one')
    if summary.optimization_status.eq('failed').any():
        raise ValueError('The final results contain failed optimizations.')
    path = results / 'final_station_results.xlsx'
    summary.to_excel(path, index=False)
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stations', type=int, nargs='?', default=2, help='Number of stations to run.')
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--validate-only', action='store_true', help='Prepare and validate the selected inputs without solving.')
    args = parser.parse_args()
    root = args.data_dir.resolve()
    source = pd.read_excel(root / MAIN_NAME)
    count = args.stations
    if count is None:
        count = int(input(f'Number of stations to run (1-{len(source)}): ').strip())
    selected = select_stations(source, count)
    if not args.validate_only and importlib.util.find_spec('gurobipy') is None:
        raise RuntimeError('Gurobi is required for the complete workflow. Install requirements.txt in this Python environment and configure a suitable Gurobi license. Use --validate-only to check inputs without a solver.')
    run_id = f'first_{count}_{datetime.now():%Y%m%d_%H%M%S}_{uuid.uuid4().hex[:8]}'
    run_dir = root / 'runs' / run_id
    run_dir.mkdir(parents=True)
    (run_dir / 'logs').mkdir()
    (run_dir / 'code').mkdir()
    manifest = {'station_count': count, 'selection': 'First N data rows in original workbook order',
                'status': 'preparing', 'completed_stages': [], 'validation_only': args.validate_only}
    manifest_path = run_dir / 'run_manifest.json'

    def save_manifest():
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')

    save_manifest()
    try:
        for name in (*STAGES, 'pipeline_io.py', 'run_pipeline.py'):
            shutil.copy2(Path(__file__).resolve().parent / name, run_dir / 'code' / name)
        manifest.update(prepare_inputs(root, run_dir, selected))
        save_manifest()
        if args.validate_only:
            run_stage(STAGES[0], run_dir, validate_only=True)
            manifest['status'] = 'validated_inputs_only'
            print('Selected load, tariff and PV inputs validated. No optimization or scientific results were produced.')
        else:
            manifest['status'] = 'running'
            for number, stage in enumerate(STAGES, 1):
                manifest['active_stage'] = stage
                save_manifest()
                print(f'\nStage {number}/{len(STAGES)}: {stage}', flush=True)
                run_stage(stage, run_dir)
                manifest['completed_stages'].append(stage)
                save_manifest()
            output = final_summary(run_dir, selected)
            manifest['final_output'] = str(output.relative_to(run_dir))
            manifest['status'] = 'completed'
            manifest.pop('active_stage', None)
            print(f'\nCompleted {count} stations. Final results: {output}')
        save_manifest()
        print(f'Run folder: {run_dir}')
        return run_dir
    except BaseException as error:
        manifest['status'] = 'interrupted' if isinstance(error, KeyboardInterrupt) else 'failed'
        manifest['error'] = str(error)
        save_manifest()
        raise


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError, FileNotFoundError, EOFError) as error:
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
