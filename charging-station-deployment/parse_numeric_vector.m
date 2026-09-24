function values = parse_numeric_vector(input)
% Parse a numeric profile without evaluating MATLAB expressions.
if iscell(input)
    assert(isscalar(input), 'Expected one profile cell.');
    input = input{1};
end
if isnumeric(input)
    values = double(input(:)');
else
    text = char(string(input));
    assert(isempty(regexp(text, '[^0-9eE+.,;\s\[\]-]', 'once')), 'Invalid characters in numeric profile.');
    text = regexprep(text, '[\[\],;]', ' ');
    tokens = regexp(strtrim(text), '\s+', 'split');
    values = str2double(tokens);
end
assert(~isempty(values) && all(isfinite(values)), 'Numeric profile contains missing or nonfinite values.');
end
