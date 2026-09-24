function test_deployment(run_solver)
% Check input validation and prove that repeated runs start from zero.
% test_deployment(false): no optimization; test_deployment(true): also solve region 1.
if nargin < 1, run_solver = false; end
root = fileparts(mfilename('fullpath'));
assert(isequal(parse_numeric_vector('[1, 2; 3]'),[1 2 3]));
first_directory = run_deployment([],true);
second_directory = run_deployment([],true);
first = load(fullfile(first_directory,'initial_state.mat'),'state','ids');
second = load(fullfile(second_directory,'initial_state.mat'),'state','ids');
assert(~strcmp(first_directory,second_directory),'Runs must have separate output folders.');
assert(isequaln(first,second),'Repeated input-only runs have different initial states.');
for field = {'CCS_num','MCS_num','design_CCS','design_MCS','annual_CCS','annual_MCS'}
    assert(all(first.state.(field{1})(:)==0),'Initial state is not zero: %s',field{1});
end
% Independent closed-form fixture for cost calculation.
parameters = load_parameters(root);
metadata = table(1,{parameters.electricity_country{1}},0,0,1000,26, ...
    'VariableNames',{'stop_id','Country','Latitude','Longitude','Area','LaborCostAdjust'});
state = struct('stop_id',1,'CCS_num',1,'MCS_num',0, ...
    'annual_CCS',ones(1,24,15),'annual_MCS',zeros(1,24,15));
costs = calculate_station_costs(metadata,state,parameters);
discount_sum = sum((1+parameters.discount_rate).^(-(1:15)));
capital = parameters.hare_ware_100 + parameters.installation_100;
expected_construction = capital*(1+parameters.annual_om_cost_CCS*discount_sum) + 54*max(parameters.area_charger-1000,0);
assert(abs(costs.cost_construction-expected_construction)<1e-6);
assert(abs(costs.stop_demand_total-8760*discount_sum)<1e-6);
assert(abs(costs.eletricity_cost-parameters.electricity_price(1,1))<1e-10);
% Check exact tariff boundaries and fractional demand immediately above them.
parameters.electricity_price(:,:) = repmat(1:7,size(parameters.electricity_price,1),1);
edges = [20000 499000 1999000 19999000 69999000 149999000];
for k = 1:numel(edges)
    for delta = [0 0.5 1]
        state.annual_CCS(:) = 0;
        state.annual_CCS(1,1,:) = (edges(k)+delta)/365;
        costs = calculate_station_costs(metadata,state,parameters);
        assert(abs(costs.eletricity_cost-(k+(delta>0)))<1e-10, 'Unexpected tariff at a boundary.');
    end
end
state.annual_CCS(:) = 0;
zero_costs = calculate_station_costs(metadata,state,parameters);
assert(isnan(zero_costs.total_cost),'LCOC must be undefined for zero charging demand.');
fprintf('Input, repeated-zero-start and independent cost tests passed.\n');
if run_solver
    output_directory = run_deployment(1,false);
    status = load(fullfile(output_directory,'run_status.mat'));
    assert(strcmp(status.status,'completed'),'One-region integration test did not complete.');
    fprintf('One-region integration test completed: %s\n',output_directory);
end
end
