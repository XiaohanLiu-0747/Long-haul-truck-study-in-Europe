function [state, info] = assign_charging_demand(root, zone_id, y, state, parameters)
% Allocate one region in one year against capacity already used by earlier regions.
data = load_zone_data(root, zone_id);
zone_stop_info = data.zone_stop_info;
numStops = data.numStops;
numNode = data.numNode;
maxODClasses = data.maxODClasses;
aggregated_demand_m = data.aggregated_demand_m;
aggregated_demand_n = data.aggregated_demand_n;
indicator_mat = data.indicator_mat;
[found, state_rows] = ismember(zone_stop_info.stop_id, state.stop_id);
assert(all(found), 'Some region stations are absent from the run state.');
discount_rate = parameters.discount_rate;
charging_loss = parameters.charging_loss;
electricity_country = parameters.electricity_country;
electricity_price = parameters.electricity_price;
numOD = maxODClasses;
numNodes = numNode;
re_charging_demand_CCS = sdpvar(1,numNodes,numOD,numStops,24,'full');
re_charging_demand_MCS = sdpvar(1,numNodes,numOD,numStops,24,'full');
stop_re_charging_demand_CCS = sdpvar(1,numStops,24,'full');
stop_re_charging_demand_MCS = sdpvar(1,numStops,24,'full');
stop_re_charging_supply_CCS = sdpvar(1,numStops,24,'full');
stop_re_charging_supply_MCS = sdpvar(1,numStops,24,'full');
annual_stop_charging_supply = sdpvar(1,numStops,'full');
z = binvar(numStops,7,1,'full');
linear_annual_stop_charging_supply = sdpvar(numStops,7,1,'full');
given_stop_re_charging_demand_CCS = permute(state.annual_CCS(state_rows,:,:), [3 1 2]);
given_stop_re_charging_demand_MCS = permute(state.annual_MCS(state_rows,:,:), [3 1 2]);
charger_CCS_num = state.CCS_num(state_rows);
charger_MCS_num = state.MCS_num(state_rows);
electricity_mat = zeros(numStops,7);
objective = 0;
avg_idx = 40;
for i = 1:numStops
    stopCountry = zone_stop_info.Country{i};
    idx = find(strcmp(electricity_country, stopCountry), 1);
    if ~isempty(idx)
        electricity_mat(i, :) = electricity_price(idx, :);
    else
        electricity_mat(i, :) = electricity_price(avg_idx, :);
    end
end
for i = 1:numStops
    for b = 1:7
        objective = objective + ((electricity_mat(i,b)*linear_annual_stop_charging_supply(i,b,1)/(1 - charging_loss))/((1 + discount_rate)^y));
    end
end
for i = 1:numStops
    objective = objective - ((annual_stop_charging_supply(1,i)/(1 - charging_loss))/((1 + discount_rate)^y));
end
constraints = [];
constraints = [constraints; re_charging_demand_CCS >= 0];
constraints = [constraints; re_charging_demand_MCS >= 0];
constraints = [constraints; stop_re_charging_demand_CCS >= 0];
constraints = [constraints; stop_re_charging_demand_MCS >= 0];
constraints = [constraints; stop_re_charging_supply_CCS >= 0];
constraints = [constraints; stop_re_charging_supply_MCS >= 0];
constraints = [constraints; annual_stop_charging_supply >= 0];
constraints = [constraints; linear_annual_stop_charging_supply >= 0];
for j = 1:numNodes
    for k = 1:numOD
        demand_CCS_all = cat(1, aggregated_demand_n{j,k,y});
        demand_MCS_all = cat(1, aggregated_demand_m{j,k,y});
        sum_CCS_all = squeeze(sum(re_charging_demand_CCS(1,j,k,:,:), 4))';
        sum_MCS_all = squeeze(sum(re_charging_demand_MCS(1,j,k,:,:), 4))';
        constraints = [constraints; sum_CCS_all == demand_CCS_all;sum_MCS_all == demand_MCS_all];
    end
end
for j = 1:numNodes
    for k = 1:numOD
        demand_CCS_all = cat(1, aggregated_demand_n{j,k,y});
        demand_MCS_all = cat(1, aggregated_demand_m{j,k,y});
        LHS_CCS_all = reshape(re_charging_demand_CCS(1,j,k,:,:), [1*numStops, 24]);
        LHS_MCS_all = reshape(re_charging_demand_MCS(1,j,k,:,:), [1*numStops, 24]);
        IND = reshape(indicator_mat(j,k,:), [numStops, 1]);
        IND_all = repmat(IND, 1, 1);
        RHS_CCS_all = IND_all .* repelem(demand_CCS_all, numStops, 1);
        RHS_MCS_all = IND_all .* repelem(demand_MCS_all, numStops, 1);
        constraints = [constraints;LHS_CCS_all <= RHS_CCS_all; LHS_MCS_all <= RHS_MCS_all];
    end
end
for i = 1:numStops
    sum_CCS_all = squeeze(sum(sum(re_charging_demand_CCS(1, :, :, i, :), 2), 3));
    sum_MCS_all = squeeze(sum(sum(re_charging_demand_MCS(1, :, :, i, :), 2), 3));
    rhs_CCS_all = squeeze(stop_re_charging_demand_CCS(1, i, :));
    rhs_MCS_all = squeeze(stop_re_charging_demand_MCS(1, i, :));
    constraints = [constraints; sum_CCS_all == rhs_CCS_all; sum_MCS_all == rhs_MCS_all];
end
constraints = [constraints;stop_re_charging_supply_CCS <= stop_re_charging_demand_CCS];
constraints = [constraints;stop_re_charging_supply_MCS <= stop_re_charging_demand_MCS];
for i = 1:numStops
    supply_CCS_all = reshape(stop_re_charging_supply_CCS(1, i, :), [1*24, 1]);
    supply_MCS_all = reshape(stop_re_charging_supply_MCS(1, i, :), [1*24, 1]);
    given_CCS_all = reshape(given_stop_re_charging_demand_CCS(y, i, :), [1*24, 1]);
    given_MCS_all = reshape(given_stop_re_charging_demand_MCS(y, i, :), [1*24, 1]);
    cap_CCS_all = repmat(100 * ones(24, 1) * charger_CCS_num(i), 1, 1);
    cap_MCS_all = repmat(1000 * ones(24, 1) * charger_MCS_num(i), 1, 1);
    constraints = [constraints; supply_CCS_all + given_CCS_all <= cap_CCS_all + 0.1; supply_MCS_all + given_MCS_all <= cap_MCS_all + 0.1];
end
for i = 1:numStops
    lhs_all = annual_stop_charging_supply(1, i);
    total_supply_all = sum(stop_re_charging_supply_CCS(1, i, :) + stop_re_charging_supply_MCS(1, i, :), 3);
    constraints = [constraints; lhs_all == 365 * total_supply_all];
end
bandwidth_mat = [0,20000;20001,499000;499001,1999000;1999001,19999000;19999001,69999000;69999001,149999000;149999001,999999999];
bandwidth_mat = bandwidth_mat / 10000;
for i = 1:numStops
    annual_supply_all = annual_stop_charging_supply(1, i);
    given_total_all = sum(given_stop_re_charging_demand_CCS(y, i, :) + given_stop_re_charging_demand_MCS(y, i, :), 3);
    for b = 1:7
        z_all = squeeze(z(i, b, 1));
        rhs_all = annual_supply_all + 365 * given_total_all;
        constraints = [constraints; bandwidth_mat(b,1) - 99999.9999*(1 - z_all) <= rhs_all/10000;bandwidth_mat(b,2) + 99999.9999*(1 - z_all) >= rhs_all/10000];
    end
    constraints = [constraints;sum(z(i, :, 1), 2) == 1];
end
for i = 1:numStops
    annual_supply_all = annual_stop_charging_supply(1, i);
    given_total_all = sum(given_stop_re_charging_demand_CCS(y, i, :) + given_stop_re_charging_demand_MCS(y, i, :), 3);
    for b = 1:7
        lin_supply_all = squeeze(linear_annual_stop_charging_supply(i, b, 1));
        z_all = squeeze(z(i, b, 1));
        rhs_all = annual_supply_all + 365 * given_total_all;
        constraints = [constraints;(lin_supply_all/10000) <= (rhs_all/10000) + 99999.9999 * (1 - z_all);(lin_supply_all/10000) >= (rhs_all/10000) - 99999.9999 * (1 - z_all);(lin_supply_all/10000) <= 99999.9999 * z_all];
    end
end
ops = sdpsettings('solver','+gurobi','gurobi.TimeLimit', parameters.solver_time_limit,'gurobi.TuneTimeLimit',0);
sol = optimize(constraints,objective,ops);
info = verify_solution(sol, constraints, objective, zone_id, y);
state.annual_CCS(state_rows,:,y) = state.annual_CCS(state_rows,:,y) + max(reshape(value(stop_re_charging_supply_CCS), numStops, 24),0);
state.annual_MCS(state_rows,:,y) = state.annual_MCS(state_rows,:,y) + max(reshape(value(stop_re_charging_supply_MCS), numStops, 24),0);
yalmip('clear');
end
