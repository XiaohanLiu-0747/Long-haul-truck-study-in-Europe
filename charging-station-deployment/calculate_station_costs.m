function output = calculate_station_costs(metadata, state, parameters)
% Calculate construction costs, discounted demand and electricity costs.
output = metadata;
output.CCS_num = state.CCS_num;
output.MCS_num = state.MCS_num;
count = height(metadata);
for year = 1:parameters.lifetime
    output.(sprintf('CCS_demand_year%d',year)) = encode_rows(state.annual_CCS(:,:,year));
    output.(sprintf('MCS_demand_year%d',year)) = encode_rows(state.annual_MCS(:,:,year));
end
output.cost_construction = zeros(count,1);
output.stop_demand_total = zeros(count,1);
output.overhead_cost = nan(count,1);
output.eletricity_cost = nan(count,1);
output.total_cost = nan(count,1);
upper_bounds = [20000 499000 1999000 19999000 69999000 149999000 inf];
for i = 1:count
    labor = metadata.LaborCostAdjust(i) / 26;
    capital_ccs = parameters.hare_ware_100 + parameters.installation_100 * (1-parameters.labor_cost_share) + parameters.installation_100 * parameters.labor_cost_share * labor;
    capital_mcs = parameters.hare_ware_1000 + parameters.installation_1000 * (1-parameters.labor_cost_share) + parameters.installation_1000 * parameters.labor_cost_share * labor;
    capital = capital_ccs*state.CCS_num(i) + capital_mcs*state.MCS_num(i);
    operations = capital_ccs*state.CCS_num(i)*parameters.annual_om_cost_CCS + capital_mcs*state.MCS_num(i)*parameters.annual_om_cost_MCS;
    country_row = find(strcmp(parameters.electricity_country, metadata.Country{i}),1);
    if isempty(country_row), country_row = 40; end
    demand_total = 0;
    electricity_total = 0;
    construction = capital;
    for year = 1:parameters.lifetime
        discount = (1+parameters.discount_rate)^year;
        construction = construction + operations/discount;
        demand = 365*sum(state.annual_CCS(i,:,year) + state.annual_MCS(i,:,year));
        demand_total = demand_total + demand/discount;
        assert(isfinite(demand) && demand >= 0, 'Invalid annual demand for station %g, year %d.', state.stop_id(i), year);
        % Continuous demand uses the first tariff upper bound that includes it.
        band = find(demand <= upper_bounds,1);
        electricity_total = electricity_total + demand*parameters.electricity_price(country_row,band)/discount;
    end
    construction = construction + 54*max(parameters.area_charger*(state.CCS_num(i)+state.MCS_num(i))-metadata.Area(i),0);
    output.cost_construction(i) = construction;
    output.stop_demand_total(i) = demand_total;
    if demand_total > 0
        output.overhead_cost(i) = construction/demand_total;
        output.eletricity_cost(i) = electricity_total/demand_total;
        output.total_cost(i) = output.overhead_cost(i) + output.eletricity_cost(i);
    end
end
output.has_charging_demand = output.stop_demand_total > 0;
end

function cells = encode_rows(values)
cells = cell(size(values,1),1);
for i = 1:size(values,1)
    cells{i} = ['[' strjoin(compose('%.17g',values(i,:)),',') ']'];
end
end
