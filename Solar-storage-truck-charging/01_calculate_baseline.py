"""Baseline calculation; original scientific equations retained."""
from pipeline_io import configure, station_key, pv_identifier, read_template, read_flows, PV_NAME
ROOT, INPUT_FILE, RESULT_DIR, SCENARIO_DIR = configure('baseline')
import pandas as pd
import numpy as np
import ast
from pathlib import Path
base_dir = ROOT
source_base_dir = ROOT
main_file = base_dir / 'zone_stop_info_merged_with_pv_area_pv_area_randomized_with_costs_with_LCOE.xlsx'
elec_price_file = source_base_dir / 'electricity price.xlsx'
power_price_file = source_base_dir / 'power price.xlsx'
pv_simulation_dir = source_base_dir / 'PV_simulation'
network_fee_file = base_dir / 'network fee.xlsx'
output_file = RESULT_DIR / 'baseline.xlsx'
scenario_output_file = RESULT_DIR / 'network_fee_sensitivity_results.xlsx'
discount_rate = 0.095
geo_col = 'GEO (Labels)'

def normalize_str(x):
    if isinstance(x, str):
        return x.strip().lower()
    return x

def find_column(df_columns, keywords):
    for col in df_columns:
        c = str(col).strip().lower()
        if all((k in c for k in keywords)):
            return col
    return None

def clean_share_value(x):
    if pd.isna(x):
        return np.nan
    x = float(x)
    if x > 1:
        x = x / 100.0
    return x

def parse_list_cell(val):
    if isinstance(val, (list, tuple, np.ndarray)):
        return list(val)
    if pd.isna(val):
        return []
    s = str(val).strip()
    if not s:
        return []
    try:
        return list(ast.literal_eval(s))
    except Exception:
        return []

def parse_power_profile_cell(cell):
    if pd.isna(cell):
        return []
    s = str(cell).strip()
    if not s:
        return []
    if s.startswith('[') and s.endswith(']'):
        s = s[1:-1]
    pairs = []
    for part in s.split(';'):
        part = part.strip()
        if not part:
            continue
        nums = part.split(',')
        if len(nums) < 2:
            continue
        try:
            power = float(nums[0].strip())
            minutes = float(nums[1].strip())
            pairs.append((power, minutes))
        except ValueError:
            continue
    return pairs

def get_level_column(D):
    x = D
    if x <= 20000:
        return 'level 1'
    elif 20001 <= x <= 499000:
        return 'level 2'
    elif 499001 <= x <= 1999000:
        return 'level 3'
    elif 1999001 <= x <= 19999000:
        return 'level 4'
    elif 19999001 <= x <= 69999000:
        return 'level 5'
    elif 69999001 <= x <= 149999000:
        return 'level 6'
    else:
        return 'level 7'

def get_level_value(row, D):
    col = get_level_column(D)
    return row[col]
df = pd.read_excel(main_file)
elec_df = pd.read_excel(elec_price_file)
power_df = pd.read_excel(power_price_file)
network_df = pd.read_excel(network_fee_file)
elec_df.columns = [str(c).strip() for c in elec_df.columns]
power_df.columns = [str(c).strip() for c in power_df.columns]
network_df.columns = [str(c).strip() for c in network_df.columns]
elec_df['_geo_norm'] = elec_df[geo_col].apply(normalize_str)
power_df['_geo_norm'] = power_df[geo_col].apply(normalize_str)
level_cols = [f'level {i}' for i in range(1, 8)]
for col in level_cols:
    if col in elec_df.columns:
        elec_df[col] = pd.to_numeric(elec_df[col], errors='coerce')
    if col in power_df.columns:
        power_df[col] = pd.to_numeric(power_df[col], errors='coerce')
elec_avg_candidates = elec_df[elec_df['_geo_norm'] == 'average']
power_avg_candidates = power_df[power_df['_geo_norm'] == 'average']
if elec_avg_candidates.empty:
    raise ValueError("electricity price.xlsx has no GEO (Labels) = 'average' row.")
if power_avg_candidates.empty:
    raise ValueError("power price.xlsx has no GEO (Labels) = 'average' row.")
elec_avg_row = elec_avg_candidates.iloc[0]
power_avg_row = power_avg_candidates.iloc[0]
energy_fee_col = find_column(network_df.columns, ['energy', 'fee'])
power_fee_col = find_column(network_df.columns, ['power', 'fee'])
if energy_fee_col is None or power_fee_col is None:
    raise ValueError("network fee.xlsx requires energy fee and power fee columns, for example: 'energy fee' / 'energy fee (kWh)', 'power fee' / 'power fee (EUR/kW/month)'")
network_df[energy_fee_col] = pd.to_numeric(network_df[energy_fee_col], errors='coerce')
network_df[power_fee_col] = pd.to_numeric(network_df[power_fee_col], errors='coerce')
base_energy_fee_value = network_df[energy_fee_col].dropna().mean()
base_power_fee_value = network_df[power_fee_col].dropna().mean()
if pd.isna(base_energy_fee_value) or pd.isna(base_power_fee_value):
    raise ValueError('network fee.xlsx has no valid energy fee or power fee values.')
_peak_cache = {}

def compute_peak_power_for_year(stop_id, year_idx, CCS_num, MCS_num):
    cache_key = (stop_id, year_idx, int(CCS_num or 0), int(MCS_num or 0))
    if cache_key in _peak_cache:
        return _peak_cache[cache_key]
    folder = pv_simulation_dir / station_key(stop_id)
    file_path = folder / 'hour_year15_template.xlsx'
    if not file_path.exists():
        _peak_cache[cache_key] = 0.0
        return 0.0
    df_pv = read_template(file_path)
    col_name = f'year{year_idx}'
    if col_name not in df_pv.columns:
        _peak_cache[cache_key] = 0.0
        return 0.0
    cap_kw = (CCS_num or 0) * 100 + (MCS_num or 0) * 1000
    peak = 0.0
    for _, r in df_pv.iterrows():
        cell = r[col_name]
        pairs = parse_power_profile_cell(cell)
        if not pairs:
            continue
        hour_power = sum((p * (m / 60.0) for p, m in pairs))
        if cap_kw > 0 and hour_power > cap_kw:
            hour_power = cap_kw
        if hour_power > peak:
            peak = hour_power
    _peak_cache[cache_key] = peak
    return peak
precomp = []
for idx, row in df.iterrows():
    stop_id = row['stop_id']
    country = normalize_str(row.get('Country', ''))
    stop_demand_total = row.get('stop_demand_total', np.nan)
    overhead_cost = row.get('overhead_cost', np.nan)
    info = {'idx': idx, 'stop_id': stop_id, 'stop_demand_total': stop_demand_total, 'overhead_cost': overhead_cost, 'year_terms': []}
    if not isinstance(stop_demand_total, (int, float, np.integer, np.floating)) or pd.isna(stop_demand_total) or stop_demand_total <= 0:
        precomp.append(info)
        continue
    CCS_num = 0 if pd.isna(row.get('CCS_num')) else row['CCS_num']
    MCS_num = 0 if pd.isna(row.get('MCS_num')) else row['MCS_num']
    elec_rows = elec_df[elec_df['_geo_norm'] == country]
    power_rows = power_df[power_df['_geo_norm'] == country]
    elec_row = elec_rows.iloc[0] if not elec_rows.empty else elec_avg_row
    power_row = power_rows.iloc[0] if not power_rows.empty else power_avg_row
    for year in range(1, 16):
        ccs_col = f'CCS_demand_year{year}'
        mcs_col = f'MCS_demand_year{year}'
        ccs_list = parse_list_cell(row.get(ccs_col, np.nan))
        mcs_list = parse_list_cell(row.get(mcs_col, np.nan))
        daily_demand = sum(ccs_list) + sum(mcs_list)
        D_i = daily_demand * 365.0
        if D_i <= 0:
            continue
        a_total = get_level_value(elec_row, D_i)
        share_net = get_level_value(power_row, D_i)
        share_net = clean_share_value(share_net)
        if pd.isna(a_total) or pd.isna(share_net):
            continue
        a_other = float(a_total) * (1.0 - float(share_net))
        peak_i = compute_peak_power_for_year(stop_id, year, CCS_num, MCS_num)
        discount_factor = 1.0 / (1.0 + discount_rate) ** year
        info['year_terms'].append((a_other, D_i, peak_i, discount_factor))
    precomp.append(info)

def compute_cost_from_precomp(info, energy_fee_value, power_fee_value):
    stop_demand_total = info['stop_demand_total']
    overhead_cost = info['overhead_cost']
    if not isinstance(stop_demand_total, (int, float, np.integer, np.floating)) or pd.isna(stop_demand_total) or stop_demand_total <= 0:
        elec_cost = 0.0
        network_cost = 0.0
        energy_fee_cost = 0.0
        power_fee_cost = 0.0
        total_cost = overhead_cost if pd.notna(overhead_cost) else 0.0
        return (elec_cost, total_cost, network_cost, energy_fee_cost, power_fee_cost)
    discounted_total_sum = 0.0
    discounted_network_sum = 0.0
    discounted_energy_fee_sum = 0.0
    discounted_power_fee_sum = 0.0
    for a_other, D_i, peak_i, disc in info['year_terms']:
        annual_energy_fee_cost_i = energy_fee_value * D_i
        annual_power_fee_cost_i = power_fee_value * 12.0 * peak_i
        annual_network_cost_i = annual_energy_fee_cost_i + annual_power_fee_cost_i
        annual_total_cost_i = (a_other + energy_fee_value) * D_i + annual_power_fee_cost_i
        discounted_energy_fee_sum += annual_energy_fee_cost_i * disc
        discounted_power_fee_sum += annual_power_fee_cost_i * disc
        discounted_network_sum += annual_network_cost_i * disc
        discounted_total_sum += annual_total_cost_i * disc
    eletricity_cost = discounted_total_sum / stop_demand_total
    network_cost = discounted_network_sum / stop_demand_total
    energy_fee_cost = discounted_energy_fee_sum / stop_demand_total
    power_fee_cost = discounted_power_fee_sum / stop_demand_total
    total_cost = eletricity_cost if pd.isna(overhead_cost) else eletricity_cost + overhead_cost
    return (eletricity_cost, total_cost, network_cost, energy_fee_cost, power_fee_cost)
base_elec_costs = []
base_total_costs = []
base_network_costs = []
base_energy_fee_costs = []
base_power_fee_costs = []
for info in precomp:
    e_cost, t_cost, n_cost, ef_cost, pf_cost = compute_cost_from_precomp(info, energy_fee_value=base_energy_fee_value, power_fee_value=base_power_fee_value)
    base_elec_costs.append(e_cost)
    base_total_costs.append(t_cost)
    base_network_costs.append(n_cost)
    base_energy_fee_costs.append(ef_cost)
    base_power_fee_costs.append(pf_cost)
df['eletricity_cost'] = base_elec_costs
df['network_cost'] = base_network_costs
df['energy_fee_cost'] = base_energy_fee_costs
df['power_fee_cost'] = base_power_fee_costs
df['total_cost'] = base_total_costs
df['total_cost_baseline'] = df['total_cost']
df.to_excel(output_file, index=False)
print(f'Done. Base case updated file saved to: {output_file}')
print(f'Base energy fee mean used: {base_energy_fee_value}')
print(f'Base power fee mean used: {base_power_fee_value}')
scenario_rows = []
for _, nf in network_df.iterrows():
    energy_fee = nf[energy_fee_col]
    power_fee = nf[power_fee_col]
    if pd.isna(energy_fee) or pd.isna(power_fee):
        continue
    energy_fee = float(energy_fee)
    power_fee = float(power_fee)
    for info in precomp:
        e_cost, t_cost, n_cost, ef_cost, pf_cost = compute_cost_from_precomp(info, energy_fee_value=energy_fee, power_fee_value=power_fee)
        scenario_rows.append({'stop_id': info['stop_id'], 'energy fee': energy_fee, 'power fee': power_fee, 'energy_fee_cost': ef_cost, 'power_fee_cost': pf_cost, 'network_cost': n_cost, 'eletricity_cost': e_cost, 'total_cost': t_cost})
scenario_df = pd.DataFrame(scenario_rows)
scenario_df.to_excel(scenario_output_file, index=False)
print(f'Done. Scenario results saved to: {scenario_output_file}')
