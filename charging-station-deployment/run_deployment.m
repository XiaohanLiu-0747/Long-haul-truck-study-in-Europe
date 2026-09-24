function output_directory = run_deployment(region_count, validate_only)
% Run the first N available regions from zero; default: all supplied regions.
% Examples: run_deployment; run_deployment(2); run_deployment(10,true)
root = fileparts(mfilename('fullpath'));
if nargin < 2, validate_only = false; end
assert(islogical(validate_only) && isscalar(validate_only), 'validate_only must be true or false.');
folders = dir(fullfile(root,'opt_model_para_table'));
names = {folders([folders.isdir]).name};
ids = str2double(names);
ids = sort(ids(isfinite(ids) & ids > 0 & ids == fix(ids)));
assert(~isempty(ids) && numel(unique(ids)) == numel(ids), 'Missing or duplicate numbered region folders.');
if nargin < 1 || isempty(region_count), region_count = numel(ids); end
validateattributes(region_count, {'numeric'}, {'scalar','integer','positive','<=',numel(ids)});
ids = ids(1:region_count);
parameters = load_parameters(root);
clear load_zone_data
metadata = table();
region_audit = table();
for region_id = ids
    data = load_zone_data(root,region_id);
    assert(data.numStops > 0 && data.numNode > 0, 'Region %d is empty.',region_id);
    for j = 1:data.numNode
        for k = 1:data.maxODClasses
            for year = 1:parameters.lifetime
                ccs = data.aggregated_demand_n{j,k,year};
                mcs = data.aggregated_demand_m{j,k,year};
                assert(numel(ccs)==24 && numel(mcs)==24 && all(isfinite([ccs mcs])) && all([ccs mcs]>=0), 'Invalid demand profile in region %d.',region_id);
                if any([ccs mcs] > 0)
                    assert(any(data.indicator_mat(j,k,:)), 'Positive demand has no eligible station in region %d.',region_id);
                end
            end
        end
    end
    metadata = [metadata; data.zone_stop_info];
    region_audit = [region_audit; table(region_id,data.numNode,data.numStops, ...
        'VariableNames',{'region_id','node_count','station_count'})];
end
% Shared stations must have consistent metadata across regions.
[~, first] = unique(metadata.stop_id,'stable');
unique_metadata = metadata(first,:);
[~, match] = ismember(metadata.stop_id,unique_metadata.stop_id);
assert(all(strcmp(metadata.Country,unique_metadata.Country(match))), 'Shared station country mismatch.');
for name = {'Latitude','Longitude','Area','LaborCostAdjust'}
    assert(all(abs(metadata.(name{1})-unique_metadata.(name{1})(match)) < 1e-8), 'Shared station metadata mismatch: %s',name{1});
end
metadata = unique_metadata;
count = height(metadata);
% Initialize capacity and demand arrays to zero for each run.
state = struct('stop_id',metadata.stop_id,'CCS_num',zeros(count,1),'MCS_num',zeros(count,1), ...
    'design_CCS',zeros(count,24),'design_MCS',zeros(count,24), ...
    'annual_CCS',zeros(count,24,parameters.lifetime),'annual_MCS',zeros(count,24,parameters.lifetime));
if ~validate_only
    assert(~isempty(which('sdpvar')) && ~isempty(which('optimize')), 'YALMIP is not on the MATLAB path.');
    assert(~isempty(which('gurobi')), 'The Gurobi MATLAB interface is not on the MATLAB path.');
end
result_root = fullfile(root,'results');
if ~isfolder(result_root), mkdir(result_root); end
[~, token] = fileparts(tempname);
output_directory = fullfile(result_root,['run_' datestr(now,'yyyymmdd_HHMMSS') '_' token]);
mkdir(output_directory);
diary(fullfile(output_directory,'run.log'));
log_cleanup = onCleanup(@() diary('off'));
writetable(region_audit,fullfile(output_directory,'selected_regions.csv'));
writetable(metadata,fullfile(output_directory,'selected_stations.xlsx'));
status = 'initialized_from_zero';
save(fullfile(output_directory,'initial_state.mat'),'state','ids','parameters','status');
fprintf('Validated %d regions and %d unique stations. Initial capacities and demands are zero.\n',region_count,count);
if validate_only
    status = 'inputs_validated_only';
    save(fullfile(output_directory,'run_status.mat'),'status','ids');
    return
end
records = struct([]);
try
    for region_id = ids
        fprintf('Capacity optimization: region %d\n',region_id);
        [state, info] = optimize_deployment(root,region_id,state,parameters);
        info.stage = "deployment";
        records = [records; info];
    end
    save(fullfile(output_directory,'deployment_state.mat'),'state','records');
    for year = 1:parameters.lifetime
        for region_id = ids
            fprintf('Demand assignment: year %d, region %d\n',year,region_id);
            [state, info] = assign_charging_demand(root,region_id,year,state,parameters);
            info.stage = "assignment";
            records = [records; info];
        end
        save(fullfile(output_directory,'checkpoint.mat'),'state','records','year');
    end
    output = calculate_station_costs(metadata,state,parameters);
    writetable(output,fullfile(output_directory,'zone_stop_info_merged.xlsx'));
    writetable(output,fullfile(output_directory,'station_results.csv'),'Delimiter',';');
    writetable(struct2table(records),fullfile(output_directory,'solver_status.csv'));
    status = 'completed';
    save(fullfile(output_directory,'run_status.mat'),'status','ids','parameters');
    fprintf('Completed. Results: %s\n',output_directory);
catch problem
    status = 'failed';
    message = problem.message;
    save(fullfile(output_directory,'failed_state.mat'),'state','records','status','message');
    save(fullfile(output_directory,'run_status.mat'),'status','message','ids');
    rethrow(problem)
end
end
