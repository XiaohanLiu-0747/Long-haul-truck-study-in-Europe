function [state, info] = optimize_deployment(root, zone_id, state, parameters)
% Determine additional capacity for one region using year-5 demand.
add_price = 54;
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
annual_om_cost_CCS = parameters.annual_om_cost_CCS;
annual_om_cost_MCS = parameters.annual_om_cost_MCS;
area_charger = parameters.area_charger;
discount_rate = parameters.discount_rate;
hare_ware_100 = parameters.hare_ware_100;
hare_ware_1000 = parameters.hare_ware_1000;
installation_100 = parameters.installation_100;
installation_1000 = parameters.installation_1000;
labor_cost_share = parameters.labor_cost_share;
lifetime = parameters.lifetime;
numOD = maxODClasses;
numNodes = numNode;
charger_CCS_num = intvar(numStops,1);
charger_MCS_num = intvar(numStops,1);
added_area = sdpvar(numStops,1);
re_charging_demand_CCS = sdpvar(numNodes,numOD,numStops,24,'full');
re_charging_demand_MCS = sdpvar(numNodes,numOD,numStops,24,'full');
stop_re_charging_demand_CCS = sdpvar(numStops,24,'full');
stop_re_charging_demand_MCS = sdpvar(numStops,24,'full');
x = binvar(numStops,1,'full');
given_CCS_num = state.CCS_num(state_rows);
given_MCS_num = state.MCS_num(state_rows);
given_stop_re_charging_demand_CCS = state.design_CCS(state_rows,:);
given_stop_re_charging_demand_MCS = state.design_MCS(state_rows,:);
objective = 0;
laborCost_adjust_factor = zone_stop_info.LaborCostAdjust;
Capital_100_list = hare_ware_100 + installation_100*(1 - labor_cost_share) +  installation_100*labor_cost_share*laborCost_adjust_factor/26;
Capital_1000_list = hare_ware_1000 + installation_1000*(1 - labor_cost_share) +  installation_1000*labor_cost_share*laborCost_adjust_factor/26;
objective = objective + sum(Capital_100_list.*charger_CCS_num) + sum(Capital_1000_list.*charger_MCS_num);
for y = 1:lifetime
    for i = 1:numStops
        objective = objective + ((Capital_100_list(i)*charger_CCS_num(i)*annual_om_cost_CCS +   Capital_1000_list(i)*charger_MCS_num(i)*annual_om_cost_MCS)/((1 + discount_rate)^y));
    end
end
for i = 1:numStops
    objective = objective + added_area(i)*add_price + 10000000*x(i);
end
constraints = [];
constraints = [constraints; added_area >= 0];
constraints = [constraints; charger_CCS_num >= 0];
constraints = [constraints; charger_MCS_num >= 0];
constraints = [constraints; re_charging_demand_CCS >= 0];
constraints = [constraints; re_charging_demand_MCS >= 0];
constraints = [constraints; stop_re_charging_demand_CCS >= 0];
constraints = [constraints; stop_re_charging_demand_MCS >= 0];
M = 1e9;
Area = zone_stop_info.Area;
for i = 1:numStops
    for t = 1:24
        constraints = [constraints; ( charger_CCS_num(i) + given_CCS_num(i) )*100 >= stop_re_charging_demand_CCS(i,t) + given_stop_re_charging_demand_CCS(i,t) ];
        constraints = [constraints; ( charger_MCS_num(i) + given_MCS_num(i) )*1000 >= stop_re_charging_demand_MCS(i,t) + given_stop_re_charging_demand_MCS(i,t)];
    end
end
for i = 1:numStops
    constraints = [constraints; added_area(i) >= (charger_CCS_num(i) + charger_MCS_num(i) + given_CCS_num(i) + given_MCS_num(i))*area_charger - Area(i)];
    constraints = [constraints; M*x(i) >= charger_CCS_num(i) + charger_MCS_num(i) + given_CCS_num(i) + given_MCS_num(i)];
end
for j = 1:numNodes
    for k = 1:numOD
        demand_CCS = aggregated_demand_n{j,k,parameters.design_year};
        demand_MCS = aggregated_demand_m{j,k,parameters.design_year};
        constraints = [constraints; squeeze(sum(re_charging_demand_CCS(j,k,:,:), 3))' == demand_CCS];
        constraints = [constraints; squeeze(sum(re_charging_demand_MCS(j,k,:,:), 3))' == demand_MCS];
    end
end
for j = 1:numNodes
    for k = 1:numOD
        demand_CCS = aggregated_demand_n{j,k,parameters.design_year};
        demand_MCS = aggregated_demand_m{j,k,parameters.design_year};
        for i = 1:numStops
            constraints = [constraints; squeeze(re_charging_demand_CCS(j,k,i,:)) <= indicator_mat(j,k,i) * demand_CCS(:)];
            constraints = [constraints; squeeze(re_charging_demand_MCS(j,k,i,:)) <= indicator_mat(j,k,i) * demand_MCS(:)];
        end
    end
end
for i = 1:numStops
    for t = 1:24
        sum_CCS = sum(sum(re_charging_demand_CCS(:, :, i, t), 1), 2);
        sum_MCS = sum(sum(re_charging_demand_MCS(:, :, i, t), 1), 2);
        constraints = [constraints;sum_CCS == stop_re_charging_demand_CCS(i,t)];
        constraints = [constraints;sum_MCS == stop_re_charging_demand_MCS(i,t)];
    end
end
ops = sdpsettings('solver','+gurobi','gurobi.TimeLimit', parameters.solver_time_limit,'gurobi.TuneTimeLimit',0);
sol = optimize(constraints,objective,ops);
info = verify_solution(sol, constraints, objective, zone_id, parameters.design_year);
new_ccs = value(charger_CCS_num);
new_mcs = value(charger_MCS_num);
assert(all(abs(new_ccs-round(new_ccs)) < 1e-4) && all(abs(new_mcs-round(new_mcs)) < 1e-4), 'Noninteger charger solution.');
state.CCS_num(state_rows) = given_CCS_num + round(new_ccs);
state.MCS_num(state_rows) = given_MCS_num + round(new_mcs);
state.design_CCS(state_rows,:) = given_stop_re_charging_demand_CCS + value(stop_re_charging_demand_CCS);
state.design_MCS(state_rows,:) = given_stop_re_charging_demand_MCS + value(stop_re_charging_demand_MCS);
yalmip('clear');
end
