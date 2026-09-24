"""Optimization calculation; original scientific equations retained."""
from pipeline_io import configure, station_key, pv_identifier, read_template, read_flows, PV_NAME
ROOT, INPUT_FILE, RESULT_DIR, SCENARIO_DIR = configure('optimization')
import os
import math
import ast
import pandas as pd
import numpy as np
import gurobipy as gp
from gurobipy import GRB
MAIN_XLSX = INPUT_FILE
ELEC_PRICE_XLSX = ROOT / 'electricity price.xlsx'
PVPWR_CSV = ROOT / PV_NAME
PVSIM_DIR = ROOT / 'PV_simulation'
POWER_PRICE = ROOT / 'power price.xlsx'
NETWORK_FEE_XLSX = ROOT / 'network fee.xlsx'
OUT_DIR = SCENARIO_DIR / 'Optimization_results'
os.makedirs(OUT_DIR, exist_ok=True)
r = 0.095
CRF_25 = r * (1 + r) ** 25 / ((1 + r) ** 25 - 1)
CRF_15 = r * (1 + r) ** 15 / ((1 + r) ** 15 - 1)
YEARS = list(range(1, 16))
MONTHS = list(range(1, 13))
HOURS_T = list(range(1, 25))
MONTH_DAYS = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}
BIGM = 100000.0

def parse_list_24(cell):
    if isinstance(cell, list):
        arr = cell
    else:
        arr = ast.literal_eval(str(cell))
    arr = [float(x) for x in arr]
    if len(arr) != 24:
        raise ValueError(f'Expect 24 values per day, got {len(arr)}')
    return arr

def parse_matrix_cell(cell):
    s = str(cell).strip()
    s = s.strip('[]').strip()
    if not s:
        return []
    parts = [p.strip() for p in s.split(';')]
    pairs = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        p = p.strip('[]')
        a, b = p.split(',')
        P = float(a.strip())
        minutes = float(b.strip())
        pairs.append((P, minutes / 60.0))
    return pairs

def crf(rate, n):
    return rate * (1 + rate) ** n / ((1 + rate) ** n - 1)

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
        return default if np.isnan(v) else v
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
print('Loading main sheet ...')
main_df = pd.read_excel(MAIN_XLSX)
main_df.columns = [str(c).strip() for c in main_df.columns]
main_df['Capacity_PV_opt'] = np.nan
main_df['Capacity_storage_opt'] = np.nan
main_df['optimization_status'] = 'not_run'
need_cols = ['stop_id', 'id_num', 'Latitude', 'Country', 'PV_install', 'PV_OM', 'storage_install', 'storage_OM', 'LCOE', 'PV_area1', 'PV_area2']
for y in YEARS:
    need_cols += [f'CCS_demand_year{y}', f'MCS_demand_year{y}']
missing = [c for c in need_cols if c not in main_df.columns]
if missing:
    raise KeyError(f'Missing station columns: {missing}')
print('Loading electricity price table ...')
elec_df = pd.read_excel(ELEC_PRICE_XLSX)
elec_df.columns = [str(c).strip() for c in elec_df.columns]
if 'GEO (Labels)' not in elec_df.columns:
    raise KeyError("electricity price.xlsx missing 'GEO (Labels)' column")
level_cols = [f'level {i}' for i in range(1, 8)]
for c in level_cols:
    if c not in elec_df.columns:
        raise KeyError(f'electricity price.xlsx missing column {c}')
elec_df_indexed = elec_df.set_index('GEO (Labels)')
elec_last_row = elec_df.loc[elec_df['GEO (Labels)'].astype(str).str.strip().str.lower() == 'average'].iloc[0]
print('Loading power price table (network share) ...')
power_df = pd.read_excel(POWER_PRICE)
power_df.columns = [str(c).strip() for c in power_df.columns]
if 'GEO (Labels)' not in power_df.columns:
    raise KeyError("power price.xlsx missing 'GEO (Labels)' column")
for c in level_cols:
    if c not in power_df.columns:
        raise KeyError(f'power price.xlsx missing column {c}')
power_df_indexed = power_df.set_index('GEO (Labels)')
power_last_row = power_df.loc[power_df['GEO (Labels)'].astype(str).str.strip().str.lower() == 'average'].iloc[0]
print('Loading network fee table ...')
network_fee_df = pd.read_excel(NETWORK_FEE_XLSX)
network_fee_df.columns = [str(c).strip() for c in network_fee_df.columns]
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
print(f'Average energy fee used = {avg_energy_fee}')
print(f'Average power fee used  = {avg_power_fee}')
print('Loading PV power table ...')
pv_df = pd.read_csv(PVPWR_CSV, sep=';')
pv_df.columns = [c.strip() for c in pv_df.columns]
need_pv_cols = ['stop_id', 'month', 'hour', 'PV_power_kW']
for c in need_pv_cols:
    if c not in pv_df.columns:
        raise KeyError(f'PV power CSV missing column {c}')
pv_grp = pv_df.groupby('stop_id')
gap_records = []

def solve_one_station(row) -> tuple:
    try:
        stop_id = int(row['stop_id'])
        country = str(row['Country']).strip()
        lat_deg = float(row['Latitude'])
        capex_pv = float(row['PV_install'])
        om_pv = float(row['PV_OM'])
        capex_sto = float(row['storage_install'])
        om_sto = float(row['storage_OM'])
        R_PV = float(row['LCOE'])
        area_pv = safe_float(row['PV_area1']) + safe_float(row['PV_area2'])
        if area_pv <= 0:
            return (np.nan, np.nan)
        if 'id' in row.index and pd.notna(row['id']):
            pv_station_id = int(row['id'])
        else:
            pv_station_id = int(row['id_num'])
        CCS = {}
        MCS = {}
        D_year_total = {}
        C_other = {}
        for y in YEARS:
            ccs = parse_list_24(row[f'CCS_demand_year{y}'])
            mcs = parse_list_24(row[f'MCS_demand_year{y}'])
            CCS[y] = ccs
            MCS[y] = mcs
            annual = 365.0 * (sum(ccs) + sum(mcs))
            D_year_total[y] = annual
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
        if pv_station_id not in pv_grp.groups:
            print(f'[WARN] stop_id {pv_station_id} has no PV profile; skipped')
            return (np.nan, np.nan)
        pv_sub = pv_grp.get_group(pv_station_id).copy()
        pv_lookup = {}
        for _, rpv in pv_sub.iterrows():
            mth = int(rpv['month'])
            hour = int(rpv['hour'])
            t = hour + 1
            pv_lookup[mth, t] = float(rpv['PV_power_kW'])
        p_pv = {(y, mth, t): (1.0 - 0.005 * (y - 1)) * pv_lookup.get((mth, t), 0.0) for y in YEARS for mth in MONTHS for t in HOURS_T}
        tmpl_path = os.path.join(PVSIM_DIR, station_key(stop_id), 'hour_year15_template.xlsx')
        if not os.path.isfile(tmpl_path):
            print(f'[WARN] {tmpl_path} does not exist; skipped')
            return (np.nan, np.nan)
        tmpl = read_template(tmpl_path)
        tmpl.columns = [str(c).strip() for c in tmpl.columns]
        if 'hour' not in tmpl.columns:
            raise KeyError("hour_year15_template.xlsx missing 'hour' column")
        for y in YEARS:
            coly = f'year{y}'
            if coly not in tmpl.columns:
                raise KeyError(f'hour_year15_template.xlsx missing {coly} column')
        sample_pairs = parse_matrix_cell(tmpl.loc[0, 'year1'])
        O = max(len(parse_matrix_cell(cell)) for col in [f'year{y}' for y in YEARS] for cell in tmpl[col])
        load_slices = {}
        for y in YEARS:
            coly = f'year{y}'
            for t in HOURS_T:
                vec = tmpl.loc[tmpl['hour'] == t, coly]
                if vec.empty:
                    pairs = []
                else:
                    pairs = parse_matrix_cell(vec.values[0])
                if len(pairs) < O:
                    pairs = pairs + [(0.0, 0.0)] * (O - len(pairs))
                elif len(pairs) > O:
                    pairs = pairs[:O]
                load_slices[y, t] = pairs
        m = gp.Model()
        m.Params.OutputFlag = 1
        Cap_PV = m.addVar(lb=0.0, name='Capacity_PV')
        Cap_ST = m.addVar(lb=0.0, name='Capacity_storage')
        Dnet = m.addVars(YEARS, lb=0.0, name='Dnet_annual')
        Togrid = m.addVars(YEARS, lb=0.0, name='Togrid_y')
        S_PV_EV = m.addVars(YEARS, MONTHS, HOURS_T, range(O), lb=0.0, name='S_PV_to_EV')
        S_ST_EV = m.addVars(YEARS, MONTHS, HOURS_T, range(O), lb=0.0, name='S_storage_to_EV')
        S_PV_ST = m.addVars(YEARS, MONTHS, HOURS_T, range(O), lb=0.0, name='S_PV_to_storage')
        S_grid_ST = m.addVars(YEARS, MONTHS, HOURS_T, range(O), lb=0.0, name='S_grid_to_storage')
        E_anchor = m.addVars(YEARS, MONTHS, lb=0.0, name='E_anchor')
        E_ST = m.addVars(YEARS, MONTHS, range(0, 25), lb=0.0, name='E_storage')
        X_mode = m.addVars(YEARS, MONTHS, HOURS_T, vtype=GRB.BINARY, name='x_storage_mode')
        P_month_max = m.addVars(YEARS, MONTHS, lb=0.0, name='P_month_max')
        tilt_rad = math.radians(lat_deg)
        m.addConstr(Cap_PV / 0.327 * 1.63 * math.cos(tilt_rad) <= 0.8 * area_pv, name='PV_area')
        for y in YEARS:
            expr_ev_year = gp.LinExpr()
            for mth in MONTHS:
                daym = MONTH_DAYS[mth]
                for t in HOURS_T:
                    expr_ev_year += daym * gp.quicksum((S_PV_EV[y, mth, t, o] + S_ST_EV[y, mth, t, o] - S_grid_ST[y, mth, t, o] for o in range(O)))
            m.addConstr(Dnet[y] == 365.0 * sum(CCS[y]) + 365.0 * sum(MCS[y]) - expr_ev_year, name=f'Dnet_balance_y{y}')
            expr_grid = gp.LinExpr()
            for mth in MONTHS:
                daym = MONTH_DAYS[mth]
                for t in HOURS_T:
                    pv_avail = Cap_PV / 0.327 * p_pv[y, mth, t]
                    used_pv = gp.quicksum((S_PV_EV[y, mth, t, o] + S_PV_ST[y, mth, t, o] for o in range(O)))
                    expr_grid += daym * (pv_avail - used_pv)
            m.addConstr(Togrid[y] == expr_grid, name=f'Togrid_def_y{y}')
            for mth in MONTHS:
                for t in HOURS_T:
                    pairs = load_slices[y, t]
                    for o in range(O):
                        P_kW, dh = pairs[o]
                        m.addConstr(S_PV_EV[y, mth, t, o] + S_ST_EV[y, mth, t, o] <= P_kW * dh, name=f'LoadCap_y{y}_m{mth}_t{t}_o{o}')
                    for o in range(O):
                        _, dh = pairs[o]
                        m.addConstr(S_PV_EV[y, mth, t, o] + S_PV_ST[y, mth, t, o] <= Cap_PV / 0.327 * p_pv[y, mth, t] * dh, name=f'PVcap_slice_y{y}_m{mth}_t{t}_o{o}')
                    expr_grid_hour = gp.LinExpr()
                    for o in range(O):
                        P_kW, dh = pairs[o]
                        expr_grid_hour += P_kW * dh - S_PV_EV[y, mth, t, o] - S_ST_EV[y, mth, t, o] + S_grid_ST[y, mth, t, o]
                    m.addConstr(expr_grid_hour <= P_month_max[y, mth], name=f'Peak_power_y{y}_m{mth}_t{t}')
                    for o in range(O):
                        _, dh = pairs[o]
                        m.addConstr(S_ST_EV[y, mth, t, o] <= Cap_ST * dh, name=f'ST_dis_max_slice_y{y}_m{mth}_t{t}_o{o}')
                        m.addConstr(S_PV_ST[y, mth, t, o] + S_grid_ST[y, mth, t, o] <= Cap_ST * dh, name=f'ST_chg_max_slice_y{y}_m{mth}_t{t}_o{o}')
                    m.addConstr(gp.quicksum((S_PV_ST[y, mth, t, o] + S_grid_ST[y, mth, t, o] for o in range(O))) <= BIGM * (1 - X_mode[y, mth, t]), name=f'Mode_charge_limit_y{y}_m{mth}_t{t}')
                    m.addConstr(gp.quicksum((S_ST_EV[y, mth, t, o] for o in range(O))) <= BIGM * X_mode[y, mth, t], name=f'Mode_discharge_limit_y{y}_m{mth}_t{t}')
                    m.addConstr(E_ST[y, mth, t] == E_ST[y, mth, t - 1] - gp.quicksum((S_ST_EV[y, mth, t, o] for o in range(O))) + gp.quicksum((S_PV_ST[y, mth, t, o] for o in range(O))) + gp.quicksum((S_grid_ST[y, mth, t, o] for o in range(O))), name=f'ST_energy_bal_y{y}_m{mth}_t{t}')
                for t in range(0, 25):
                    m.addConstr(E_ST[y, mth, t] >= 0.1 * Cap_ST, name=f'ST_soc_min_y{y}_m{mth}_t{t}')
                    m.addConstr(E_ST[y, mth, t] <= Cap_ST, name=f'ST_soc_max_y{y}_m{mth}_t{t}')
                m.addConstr(E_anchor[y, mth] >= 0.1 * Cap_ST)
                m.addConstr(E_anchor[y, mth] <= Cap_ST)
                m.addConstr(E_ST[y, mth, 0] == E_anchor[y, mth])
                m.addConstr(E_ST[y, mth, 24] == E_anchor[y, mth])
        obj = gp.LinExpr()
        obj += capex_pv * Cap_PV * CRF_25 + om_pv * Cap_PV
        obj += capex_sto * Cap_ST * CRF_15 + om_sto * Cap_ST
        for y in YEARS:
            pv_disc = 1.0 / (1 + r) ** y
            energy_cost_y = (C_other[y] + avg_energy_fee) * Dnet[y]
            power_cost_y = avg_power_fee * gp.quicksum((P_month_max[y, mth] for mth in MONTHS))
            obj += CRF_15 * pv_disc * (energy_cost_y + power_cost_y - R_PV * Togrid[y])
        m.setObjective(obj, GRB.MINIMIZE)
        m.Params.MIPGap = 0.01
        m.Params.TimeLimit = 100
        m.optimize()
        gap_val = float(m.MIPGap) if m.SolCount > 0 else np.nan
        gap_records.append({'stop_id': stop_id, 'mip_gap': gap_val, 'status': int(m.status), 'sol_count': int(m.SolCount)})
        if m.status == GRB.OPTIMAL:
            pass
        elif m.SolCount > 0:
            print(f'[WARN] stop_id={stop_id} has an incumbent but optimality is unproven (status={m.status}); using the best incumbent')
        else:
            print(f'[WARN] stop_id={stop_id} has no feasible solution (status={m.status})')
            return (np.nan, np.nan)
        station_dir = os.path.join(OUT_DIR, station_key(stop_id))
        os.makedirs(station_dir, exist_ok=True)

        def dump_var_to_csv(var, name, O_local):
            data = []
            for yy in YEARS:
                for mm in MONTHS:
                    for tt in HOURS_T:
                        for oo in range(O_local):
                            v = var[yy, mm, tt, oo].X
                            data.append((yy, mm, tt, oo, v))
            df_out = pd.DataFrame(data, columns=['year', 'month', 'hour', 'o', 'value'])
            out_path = os.path.join(station_dir, f'{name}.csv')
            df_out.to_csv(out_path, sep=';', index=False, encoding='utf-8-sig')
        dump_var_to_csv(S_PV_EV, 'S_PV_EV', O)
        dump_var_to_csv(S_ST_EV, 'S_ST_EV', O)
        dump_var_to_csv(S_PV_ST, 'S_PV_ST', O)
        dump_var_to_csv(S_grid_ST, 'S_grid_ST', O)
        meta_row = {'stop_id': stop_id, 'Capacity_PV_opt': Cap_PV.X, 'Capacity_storage_opt': Cap_ST.X}
        for yy in YEARS:
            for mm in MONTHS:
                meta_row[f'E_anchor_y{yy}_m{mm}'] = E_anchor[yy, mm].X
        meta = pd.DataFrame([meta_row])
        meta.to_csv(os.path.join(station_dir, 'meta.csv'), sep=';', index=False, encoding='utf-8-sig')
        return (Cap_PV.X, Cap_ST.X)
    except Exception as e:
        print(f"[ERROR] stop_id={row.get('stop_id')} failed: {e}")
        gap_records.append({'stop_id': row.get('stop_id'), 'mip_gap': np.nan, 'status': 'error', 'sol_count': 0, 'error': str(e)})
        return (np.nan, np.nan)
total = len(main_df)
for idx, row in main_df.iterrows():
    pv_area_sum = safe_float(row['PV_area1']) + safe_float(row['PV_area2'])
    if pv_area_sum <= 0:
        main_df.at[idx, 'optimization_status'] = 'no_pv_area'
        continue
    cap_pv, cap_st = solve_one_station(row)
    main_df.at[idx, 'optimization_status'] = 'solved' if np.isfinite(cap_pv) and np.isfinite(cap_st) else 'failed'
    main_df.at[idx, 'Capacity_PV_opt'] = cap_pv
    main_df.at[idx, 'Capacity_storage_opt'] = cap_st
    print(f'Progress: {idx + 1}/{total}')
main_df.to_excel(SCENARIO_DIR / 'optimized.xlsx', index=False)
print('Saved optimized capacities.')
gap_df = pd.DataFrame(gap_records)
gap_out = os.path.join(OUT_DIR, 'mip_gap_summary.xlsx')
gap_df.to_excel(gap_out, index=False)
print(f'Saved solver gap summary: {gap_out}')
if main_df['optimization_status'].eq('failed').any():
    raise RuntimeError('Some stations failed optimization; inspect mip_gap_summary.xlsx before postprocessing.')
