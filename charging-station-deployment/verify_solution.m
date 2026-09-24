function info = verify_solution(sol, constraints, objective, zone_id, year)
% Do not commit infeasible or missing solutions to the station state.
assert(ismember(sol.problem, [0 3]), 'Solver failed for region %d, year %d: %s', zone_id, year, sol.info);
residuals = check(constraints);
objective_value = value(objective);
assert(all(isfinite(residuals)) && all(residuals >= -1e-5) && isfinite(objective_value), ...
    'No verified feasible solution for region %d, year %d (status %d).', zone_id, year, sol.problem);
info = struct('region_id', zone_id, 'year', year, 'problem_code', sol.problem, ...
    'objective', objective_value, 'minimum_constraint_residual', min(residuals), ...
    'solver_message', string(sol.info));
end
