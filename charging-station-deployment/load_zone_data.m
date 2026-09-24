function data = load_zone_data(root, zone_id)
% Read and cache one region, with identical OD ordering for demands and eligibility.
persistent cache
if isempty(cache), cache = containers.Map('KeyType','char','ValueType','any'); end
zoneFolder = fullfile(root, 'opt_model_para_table', num2str(zone_id));
if isKey(cache, zoneFolder), data = cache(zoneFolder); return; end
nodeSetFile = fullfile(zoneFolder, 'node_set.xlsx');
nodeSetFile_new = fullfile(zoneFolder, 'node_set_with_stop.xlsx');
zoneStopInfoFile = fullfile(zoneFolder, 'zone_stop_info.xlsx');
node_set = readtable(nodeSetFile);
node_set_new = readtable(nodeSetFile_new);
zone_stop_info = readtable(zoneStopInfoFile);
required = {'stop_id','Country','Latitude','Longitude','Area','LaborCostAdjust'};
assert(all(ismember(required,zone_stop_info.Properties.VariableNames)), 'Missing region station metadata.');
zone_stop_info = zone_stop_info(:,required);
zone_stop_info.Country = cellstr(string(zone_stop_info.Country));
for name = {'stop_id','Latitude','Longitude','Area','LaborCostAdjust'}
    zone_stop_info.(name{1}) = str2double(string(zone_stop_info.(name{1})));
    assert(all(isfinite(zone_stop_info.(name{1}))), 'Nonfinite station metadata: %s',name{1});
end
assert(all(zone_stop_info.stop_id==fix(zone_stop_info.stop_id)) && numel(unique(zone_stop_info.stop_id))==height(zone_stop_info), 'Invalid or duplicate station IDs.');
assert(all(zone_stop_info.Area>=0 & zone_stop_info.LaborCostAdjust>=0), 'Negative area or labor costs.');
numNode = height(node_set);
numStops = height(zone_stop_info);
merged_od_results = cell(numNode, 1);
for j = 1:numNode
    node_id = char(string(node_set.node_id(j)));
    csvFile = fullfile(zoneFolder, [node_id, '.csv']);
    if ~exist(csvFile, 'file')
        error('Missing node input: %s', csvFile);
    end
    opts = detectImportOptions(csvFile, 'Delimiter', ',','VariableNamingRule', 'preserve');
    opts = setvartype(opts, {'Selected_Nodes', 'Stop'}, 'char');
    T = readtable(csvFile, opts);
    T.Selected_Nodes = cellstr(string(T.Selected_Nodes));
    reqCols = {'Selected_Nodes', 'charging_demand_m', 'charging_demand_n', 'ChargingAdjustmentFactors', 'Stop'};
    if ~all(ismember(reqCols, T.Properties.VariableNames))
        error('File %s is missing required columns.', csvFile);
    end
    if isnumeric(T.Selected_Nodes)
        SelectedNodesStr = arrayfun(@num2str, T.Selected_Nodes, 'UniformOutput', false);
    elseif iscell(T.Selected_Nodes)
        SelectedNodesStr = T.Selected_Nodes;
    else
        SelectedNodesStr = cellstr(T.Selected_Nodes);
    end
    uniqueGroups = unique(SelectedNodesStr, 'stable');
    numOD_classes = numel(uniqueGroups);
    odResults = repmat(struct('SelectedNodes', [], 'agg_demand_m', {{}}, 'agg_demand_n', {{}}, 'CAFactors', []), numOD_classes, 1);
    for g = 1:numOD_classes
        groupVal = uniqueGroups{g};
        idx = find(strcmp(SelectedNodesStr, groupVal));
        numRows = numel(idx);
        mat_m = zeros(numRows, 24);
        mat_n = zeros(numRows, 24);
        mat_factor = zeros(numRows, 15);
        for r = 1:numRows
            row_idx = idx(r);
            mat_m(r, :) = parse_numeric_vector(T.charging_demand_m{row_idx});
            mat_n(r, :) = parse_numeric_vector(T.charging_demand_n{row_idx});
            mat_factor(r, :) = parse_numeric_vector(T.ChargingAdjustmentFactors{row_idx});
        end
        agg_profiles_m = cell(1,15);
        agg_profiles_n = cell(1,15);
        for yr = 1:15
            adj_profiles_m = mat_factor(:,yr) .* mat_m;
            adj_profiles_n = mat_factor(:,yr) .* mat_n;
            agg_profiles_m{yr} = sum(adj_profiles_m, 1);
            agg_profiles_n{yr} = sum(adj_profiles_n, 1);
        end
        odResults(g).SelectedNodes = groupVal;
        odResults(g).agg_demand_m = agg_profiles_m;
        odResults(g).agg_demand_n = agg_profiles_n;
        odResults(g).CAFactors = mat_factor(1,:);
    end
    merged_od_results{j} = odResults;
end
maxODClasses = 0;
for j = 1:numNode
    if ~isempty(merged_od_results{j})
        maxODClasses = max(maxODClasses, numel(merged_od_results{j}));
    end
end
aggregated_demand_m = cell(numNode, maxODClasses, 15);
aggregated_demand_n = cell(numNode, maxODClasses, 15);
for j = 1:numNode
    odResults = merged_od_results{j};
    if isempty(odResults)
        continue;
    end
    for k = 1:numel(odResults)
        for yr = 1:15
            aggregated_demand_m{j, k, yr} = odResults(k).agg_demand_m{yr};
            aggregated_demand_n{j, k, yr} = odResults(k).agg_demand_n{yr};
        end
    end
end
for i = 1:numNode
    for j = 1:maxODClasses
        for k = 1:15
            if isempty(aggregated_demand_m{i,j,k})
                aggregated_demand_m{i,j,k} = zeros(1,24);
            end
            if isempty(aggregated_demand_n{i,j,k})
                aggregated_demand_n{i,j,k} = zeros(1,24);
            end
        end
    end
end
indicator_mat = zeros(numNode, maxODClasses, numStops);
for j = 1:numNode
    node_id = char(string(node_set.node_id(j)));
    csvFile = fullfile(zoneFolder, [node_id, '.csv']);
    if ~exist(csvFile, 'file')
        error('Missing node input: %s', csvFile);
    end
    opts = detectImportOptions(csvFile, 'Delimiter', ',', 'VariableNamingRule', 'preserve');
    opts = setvartype(opts, {'Selected_Nodes', 'Stop'}, 'char');
    T = readtable(csvFile, opts);
    T.Selected_Nodes = cellstr(string(T.Selected_Nodes));
    if ~ismember('Selected_Nodes', T.Properties.VariableNames) || ~ismember('Stop', T.Properties.VariableNames)
        error('File %s is missing required columns.', csvFile);
    end
    uniqueGroups = unique(T.Selected_Nodes, 'stable');
    for k = 1:length(uniqueGroups)
        groupVal = uniqueGroups{k};
        if contains(groupVal, ',')
            node_ids = strsplit(groupVal, ',');
            node_ids = strtrim(node_ids);
        else
            node_ids = {groupVal};
        end
        stops_all = [];
        for p = 1:length(node_ids)
            currentNodeId = str2double(node_ids{p});
            idx_node = find(str2double(string(node_set_new.node_id)) == currentNodeId);
            if ~isempty(idx_node)
                stopStr = node_set_new.stop(idx_node(1));
                stops_numeric = parse_numeric_vector(stopStr);
                stops_all = [stops_all, stops_numeric];
            end
        end
        stops_all = unique(stops_all);
        for s = 1:numStops
            current_stop = zone_stop_info.stop_id(s);
            if any(abs(stops_all - current_stop) < 1e-6)
                indicator_mat(j, k, s) = 1;
            end
        end
    end
end
data = struct('zone_stop_info', zone_stop_info, 'numNode', numNode, ...
    'numStops', numStops, 'maxODClasses', maxODClasses, ...
    'aggregated_demand_m', {aggregated_demand_m}, ...
    'aggregated_demand_n', {aggregated_demand_n}, 'indicator_mat', indicator_mat);
cache(zoneFolder) = data;
end
