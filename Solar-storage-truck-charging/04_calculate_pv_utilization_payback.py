"""Payback calculation; original scientific equations retained."""
from pipeline_io import configure, station_key, pv_identifier, read_template, read_flows, PV_NAME
ROOT, INPUT_FILE, RESULT_DIR, SCENARIO_DIR = configure('payback')
import os
import ast
import numpy as np
import pandas as pd
MAIN_XLSX = INPUT_FILE
NETWORK_FEE_XLSX = ROOT / 'network fee.xlsx'
ELEC_PRICE_XLSX = ROOT / 'electricity price.xlsx'
POWER_PRICE = ROOT / 'power price.xlsx'
PVPWR_CSV = ROOT / PV_NAME
PVSIM_DIR = ROOT / 'PV_simulation'
OPT_RES_DIR = SCENARIO_DIR / 'Optimization_results'
OUT_DIR = SCENARIO_DIR
os.makedirs(OUT_DIR, exist_ok=True)
OUT_XLSX = os.path.join(OUT_DIR, 'pv_utilization_payback_point_table.xlsx')
r = 0.095
YEARS = list(range(1, 16))
MONTHS = list(range(1, 13))
HOURS_T = list(range(1, 25))
MONTH_DAYS = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}

def parse_list_24(cell):
    if isinstance(cell, list):
        arr = cell
    else:
        arr = ast.literal_eval(str(cell))
    arr = [float(x) for x in arr]
    if len(arr) != 24:
        raise ValueError(f'Expect 24 values, got {len(arr)}')
    return arr

def parse_matrix_cell(cell):
    s = str(cell).strip()
    s = s.strip('[]').strip()
    if not s:
        return []
    parts = [p.strip() for p in s.split(';')]
    pairs = []
    for p in parts:
        if not p:
            continue
        p = p.strip('[]')
        a, b = p.split(',')
        P = float(a.strip())
        minutes = float(b.strip())
        pairs.append((P, minutes / 60.0))
    return pairs

def tier_price(annual_kwh, row_levels):
    x = annual_kwh
    if x <= 20000:
        return row_levels['level 1']
    elif 20001 <= x <= 499000:
        return row_levels['level 2']
    elif 499001 <= x <= 1999000:
        return row_levels['level 3']
    elif 1999001 <= x <= 19999000:
        return row_levels['level 4']
    elif 19999001 <= x <= 69999000:
        return row_levels['level 5']
    elif 69999001 <= x <= 149999000:
        return row_levels['level 6']
    else:
        return row_levels['level 7']

def safe_float(x, default=0.0):
    try:
        v = float(x)
        if np.isnan(v):
            return default
        return v
    except Exception:
        return default

def clean_share_value(x):
    x = float(x)
    if x > 1:
        x = x / 100.0
    return x

def find_column(df_columns, keywords):
    for col in df_columns:
        c = str(col).strip().lower()
        if all((k in c for k in keywords)):
            return col
    return None
main_df = pd.read_excel(MAIN_XLSX)
elec_df = pd.read_excel(ELEC_PRICE_XLSX)
elec_df.columns = [str(c).strip() for c in elec_df.columns]
power_df = pd.read_excel(POWER_PRICE)
power_df.columns = [str(c).strip() for c in power_df.columns]
network_fee_df = pd.read_excel(NETWORK_FEE_XLSX)
network_fee_df.columns = [str(c).strip() for c in network_fee_df.columns]
pv_df = pd.read_csv(PVPWR_CSV, sep=';')
pv_df.columns = [c.strip() for c in pv_df.columns]
level_cols = [f'level {i}' for i in range(1, 8)]
for df_name, df_obj in [('electricity price.xlsx', elec_df), ('power price.xlsx', power_df)]:
    if 'GEO (Labels)' not in df_obj.columns:
        raise KeyError(f"{df_name} missing 'GEO (Labels)' column")
    for c in level_cols:
        if c not in df_obj.columns:
            raise KeyError(f'{df_name} missing column {c}')
for c in ['stop_id', 'month', 'hour', 'PV_power_kW']:
    if c not in pv_df.columns:
        raise KeyError(f'PV power CSV missing column {c}')
elec_df_indexed = elec_df.set_index('GEO (Labels)')
elec_last_row = elec_df.loc[elec_df['GEO (Labels)'].astype(str).str.strip().str.lower() == 'average'].iloc[0]
power_df_indexed = power_df.set_index('GEO (Labels)')
power_last_row = power_df.loc[power_df['GEO (Labels)'].astype(str).str.strip().str.lower() == 'average'].iloc[0]
energy_fee_col = find_column(network_fee_df.columns, ['energy', 'fee'])
power_fee_col = find_column(network_fee_df.columns, ['power', 'fee'])
if energy_fee_col is None or power_fee_col is None:
    raise KeyError('network fee.xlsx requires energy fee and power fee columns')
network_fee_df[energy_fee_col] = pd.to_numeric(network_fee_df[energy_fee_col], errors='coerce')
network_fee_df[power_fee_col] = pd.to_numeric(network_fee_df[power_fee_col], errors='coerce')
avg_energy_fee = network_fee_df[energy_fee_col].dropna().mean()
avg_power_fee = network_fee_df[power_fee_col].dropna().mean()
if pd.isna(avg_energy_fee) or pd.isna(avg_power_fee):
    raise ValueError('network fee.xlsx has no valid energy fee or power fee values')
print(f'Average energy fee used: {avg_energy_fee}')
print(f'Average power fee used: {avg_power_fee}')
pv_grp = pv_df.groupby('stop_id')
point_rows = []
processed = 0
total = len(main_df)
for idx, row in main_df.iterrows():
    cap_pv_opt = row.get('Capacity_PV_opt')
    if row.get('optimization_status') != 'solved' or pd.isna(cap_pv_opt) or cap_pv_opt < 0:
        continue
    stop_id = row.get('stop_id')
    id_num = pv_identifier(row)
    country = str(row.get('Country')).strip()
    capex_pv = safe_float(row.get('PV_install'))
    om_pv = safe_float(row.get('PV_OM'))
    capex_st = safe_float(row.get('storage_install'))
    om_st = safe_float(row.get('storage_OM'))
    R_PV = safe_float(row.get('LCOE'))
    cap_pv = safe_float(cap_pv_opt)
    cap_st = safe_float(row.get('Capacity_storage_opt'))
    D_annual = {}
    C_other = {}
    for y in YEARS:
        ccs = parse_list_24(row[f'CCS_demand_year{y}'])
        mcs = parse_list_24(row[f'MCS_demand_year{y}'])
        annual = 365.0 * (sum(ccs) + sum(mcs))
        D_annual[y] = annual
        if country in elec_df_indexed.index:
            rlv_e = elec_df_indexed.loc[country]
        else:
            rlv_e = elec_last_row
        elec_levels = {f'level {i}': float(rlv_e[f'level {i}']) for i in range(1, 8)}
        a_total = tier_price(annual, elec_levels)
        if country in power_df_indexed.index:
            rlv_p = power_df_indexed.loc[country]
        else:
            rlv_p = power_last_row
        share_levels = {f'level {i}': float(rlv_p[f'level {i}']) for i in range(1, 8)}
        share_net = tier_price(annual, share_levels)
        share_net = clean_share_value(share_net)
        C_other[y] = a_total * (1.0 - share_net)
    s_dir = os.path.join(OPT_RES_DIR, station_key(stop_id))

    def read_flow_csv(name):
        f = os.path.join(s_dir, f'{name}.csv')
        if not os.path.isfile(f):
            raise FileNotFoundError(f)
        df = read_flows(f)
        df.columns = [c.strip() for c in df.columns]
        for c in ['year', 'month', 'hour', 'o', 'value']:
            if c not in df.columns:
                raise KeyError(f'{name}.csv missing column {c}')
        return df
    df_pv_ev = read_flow_csv('S_PV_EV')
    df_st_ev = read_flow_csv('S_ST_EV')
    df_pv_st = read_flow_csv('S_PV_ST')
    df_grid_st = read_flow_csv('S_grid_ST')

    def agg_year_energy(df):
        if df is None or df.empty:
            return {y: 0.0 for y in YEARS}
        tmp = df.groupby(['year', 'month', 'hour'], as_index=False)['value'].sum()
        tmp['days'] = tmp['month'].map(MONTH_DAYS).astype(float)
        tmp['val_y'] = tmp['value'] * tmp['days']
        s = tmp.groupby('year')['val_y'].sum()
        out = {int(k): float(v) for k, v in s.items()}
        for y in YEARS:
            out.setdefault(y, 0.0)
        return out

    def agg_slice(df):
        if df is None or df.empty:
            return {}
        tmp = df.groupby(['year', 'month', 'hour'], as_index=False)['value'].sum()
        tmp['t'] = tmp['hour'].astype(int)
        key = list(zip(tmp['year'].astype(int), tmp['month'].astype(int), tmp['t']))
        return dict(zip(key, tmp['value'].astype(float)))
    EV_from_PV = agg_year_energy(df_pv_ev)
    EV_from_ST = agg_year_energy(df_st_ev)
    GRID_to_ST = agg_year_energy(df_grid_st)
    pv_ev_y_mt = agg_slice(df_pv_ev)
    pv_st_y_mt = agg_slice(df_pv_st)
    st_ev_y_mt = agg_slice(df_st_ev)
    grid_st_y_mt = agg_slice(df_grid_st)
    p_pv = {}
    if pd.notna(id_num) and int(id_num) in pv_grp.groups:
        pv_sub = pv_grp.get_group(int(id_num))
        base_map = {}
        for _, rpv in pv_sub.iterrows():
            m = int(rpv['month'])
            t = int(rpv['hour']) + 1
            base_map[m, t] = float(rpv['PV_power_kW'])
        for y in YEARS:
            degr = 1.0 - 0.005 * (y - 1)
            for m in MONTHS:
                for t in HOURS_T:
                    p_pv[y, m, t] = degr * base_map.get((m, t), 0.0)
    else:
        for y in YEARS:
            for m in MONTHS:
                for t in HOURS_T:
                    p_pv[y, m, t] = 0.0
    Dnet_annual = {}
    Togrid_y = {}
    total_pv_generation_15yr = 0.0
    total_pv_non_export_15yr = 0.0
    for y in YEARS:
        d_total = D_annual[y]
        ev_supply = EV_from_PV.get(y, 0.0) + EV_from_ST.get(y, 0.0)
        grid_to_st = GRID_to_ST.get(y, 0.0)
        Dnet_annual[y] = d_total - ev_supply + grid_to_st
        tg_sum = 0.0
        for m in MONTHS:
            dm = MONTH_DAYS[m]
            for t in HOURS_T:
                pv_available_day = cap_pv / 0.327 * p_pv[y, m, t]
                pv_used_day = pv_ev_y_mt.get((y, m, t), 0.0) + pv_st_y_mt.get((y, m, t), 0.0)
                total_pv_generation_15yr += dm * pv_available_day
                total_pv_non_export_15yr += dm * pv_used_day
                tg_sum += dm * (pv_available_day - pv_used_day)
        Togrid_y[y] = tg_sum
    if total_pv_generation_15yr > 0:
        pv_utilization_rate = total_pv_non_export_15yr / total_pv_generation_15yr
    else:
        pv_utilization_rate = np.nan
    tmpl_path = os.path.join(PVSIM_DIR, str(int(stop_id)), 'hour_year15_template.xlsx')
    load_hour_energy = {}
    if os.path.isfile(tmpl_path):
        tmpl = read_template(tmpl_path)
        tmpl.columns = [str(c).strip() for c in tmpl.columns]
        if 'hour' not in tmpl.columns:
            raise KeyError("hour_year15_template.xlsx missing 'hour' column")
        for y in YEARS:
            coly = f'year{y}'
            if coly not in tmpl.columns:
                raise KeyError(f'hour_year15_template.xlsx missing {coly} column')
        for y in YEARS:
            coly = f'year{y}'
            for t in HOURS_T:
                vec = tmpl.loc[tmpl['hour'] == t, coly]
                pairs = parse_matrix_cell(vec.values[0]) if not vec.empty else []
                load_hour_energy[y, t] = float(sum((P_kW * dh for P_kW, dh in pairs)))
    else:
        for y in YEARS:
            for t in HOURS_T:
                load_hour_energy[y, t] = 0.0
    P_month_max = {(y, m): 0.0 for y in YEARS for m in MONTHS}
    P_month_max0 = {(y, m): 0.0 for y in YEARS for m in MONTHS}
    for y in YEARS:
        for m in MONTHS:
            mx = 0.0
            mx0 = 0.0
            for t in HOURS_T:
                demand_hour = load_hour_energy.get((y, t), 0.0)
                grid_hour0 = demand_hour
                grid_hour = demand_hour - pv_ev_y_mt.get((y, m, t), 0.0) - st_ev_y_mt.get((y, m, t), 0.0) + grid_st_y_mt.get((y, m, t), 0.0)
                if grid_hour0 > mx0:
                    mx0 = grid_hour0
                if grid_hour > mx:
                    mx = grid_hour
            P_month_max0[y, m] = float(mx0)
            P_month_max[y, m] = float(mx)
    power_cost0_y = {y: avg_power_fee * sum((P_month_max0[y, m] for m in MONTHS)) for y in YEARS}
    power_cost_y = {y: avg_power_fee * sum((P_month_max[y, m] for m in MONTHS)) for y in YEARS}
    CAPEX_pvst = capex_pv * cap_pv + capex_st * cap_st
    if CAPEX_pvst <= 0:
        payback = 'no'
    else:
        S = {}
        for y in YEARS:
            baseline_cost_y = (C_other[y] + avg_energy_fee) * D_annual[y] + power_cost0_y[y]
            pvst_cost_y = (C_other[y] + avg_energy_fee) * Dnet_annual[y] + power_cost_y[y] - R_PV * Togrid_y[y] + om_pv * cap_pv + om_st * cap_st
            S[y] = baseline_cost_y - pvst_cost_y
        cum_disc = 0.0
        payback_year = None
        for y in YEARS:
            cum_disc += S[y] / (1.0 + r) ** y
            if cum_disc >= CAPEX_pvst:
                payback_year = y
                break
        payback = payback_year if payback_year is not None else 'no'
    point_rows.append({'stop_id': int(stop_id), 'PV utilization rate': pv_utilization_rate, 'payback': payback})
    processed += 1
    if processed % 50 == 0:
        print(f'Processed {processed}/{total} rows...')
point_df = main_df[['stop_id', 'optimization_status']].merge(pd.DataFrame(point_rows, columns=['stop_id', 'PV utilization rate', 'payback']), on='stop_id', how='left', validate='one_to_one')
point_df.to_excel(OUT_XLSX, index=False)
print(f'Done. Point table saved to:\n{OUT_XLSX}')
print(f'Rows saved: {len(point_df)}')
