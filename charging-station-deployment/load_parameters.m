function parameters = load_parameters(root)
% Load economic parameters, country labels and electricity tariffs.
required = {'annual_om_cost_CCS','annual_om_cost_MCS','area_charger', ...
    'charging_loss','discount_rate','hare_ware_100','hare_ware_1000', ...
    'installation_100','installation_1000','labor_cost_share','lifetime', ...
    'electricity_country','electricity_price'};
path = fullfile(root, 'matlab20250310.mat');
parameters = load(path, required{:});
assert(all(isfield(parameters, required)), 'Parameter MAT file is missing required variables.');
for k = 1:11
    value = parameters.(required{k});
    assert(isnumeric(value) && isscalar(value) && isfinite(value) && value >= 0, ...
        'Invalid parameter: %s', required{k});
end
assert(parameters.lifetime == 15, 'This model requires a 15-year lifetime.');
assert(parameters.charging_loss < 1 && parameters.labor_cost_share <= 1, 'Invalid loss or labor fraction.');
parameters.electricity_country = cellstr(strtrim(string(parameters.electricity_country(:))));
assert(isnumeric(parameters.electricity_price) && size(parameters.electricity_price,2) == 7, 'Expected seven electricity tariff columns.');
assert(size(parameters.electricity_price,1) == numel(parameters.electricity_country), 'Country and tariff row counts differ.');
assert(size(parameters.electricity_price,1) >= 40 && all(isfinite(parameters.electricity_price(:))), 'Missing default tariff row 40 or nonfinite prices.');
assert(numel(unique(parameters.electricity_country)) == numel(parameters.electricity_country), 'Duplicate tariff country labels.');
% Set the design year and per-model time limit.
parameters.design_year = 5;
parameters.solver_time_limit = 1000;
end
