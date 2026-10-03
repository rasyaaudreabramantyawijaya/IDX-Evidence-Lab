function build_portfolio_factor_zoo()
% Build the interactive MATLAB reference plot from the shared local JSON.
% Scores are computed once by portfolio_factors.py; MATLAB never recalculates them.

scriptDir = fileparts(mfilename('fullpath'));
rootDir = fileparts(scriptDir);
dataPath = fullfile(rootDir, 'docs', 'prototypes', 'portfolio-factor-zoo-data.json');
viewPath = fullfile(rootDir, 'docs', 'prototypes', 'portfolio-factor-zoo-view.json');
figurePath = fullfile(rootDir, 'docs', 'prototypes', 'portfolio-factor-zoo.fig');

if ~isfile(dataPath)
    error('FactorZoo:MissingArtifact', ...
        'Missing shared factor data. First run scripts/export_portfolio_factor_zoo_data.py.');
end
payload = jsondecode(fileread(dataPath));
if ~isfield(payload, 'schema_version') || ~strcmp(payload.schema_version, 'portfolio-factor-zoo.v1')
    error('FactorZoo:Schema', 'Unsupported factor-data schema. Re-export the local artifact.');
end
if ~isfield(payload, 'formula_version') || ~strcmp(payload.formula_version, 'cross-sectional-zscore.v1')
    error('FactorZoo:Formula', 'Unexpected formula version. Use the matching application code.');
end
if ~isfield(payload, 'universe') || payload.universe.count ~= 45 || ...
        ~isfield(payload, 'records') || numel(payload.records) ~= 45
    error('FactorZoo:Universe', 'Expected all 45 current LQ45 snapshot records.');
end
if ~isfield(payload, 'sources') || ~isfield(payload.sources, 'sha256') || isempty(payload.sources.sha256) || ...
        ~isfield(payload, 'as_of') || isempty(payload.as_of.price)
    error('FactorZoo:Provenance', 'Artifact lacks source fingerprint or price as-of metadata.');
end

records = payload.records(:);
xyz = nan(numel(records), 3);
lowVol = nan(numel(records), 1);
axisEligible = false(numel(records), 1);
lowVolEligible = false(numel(records), 1);
for k = 1:numel(records)
    xyz(k, 1) = factorScore(records(k), 'value');
    xyz(k, 2) = factorScore(records(k), 'momentum');
    xyz(k, 3) = factorScore(records(k), 'quality');
    lowVol(k) = factorScore(records(k), 'low_volatility');
    axisEligible(k) = all(isfinite(xyz(k, :)));
    lowVolEligible(k) = isfinite(lowVol(k));
end
if ~any(axisEligible)
    error('FactorZoo:NoPoints', 'No issuer has complete Value, Momentum, and Quality scores for the 3D chart.');
end

fig = figure('Name', 'LQ45 Factor Zoo · shared local snapshot', ...
    'Color', [0.035 0.055 0.08], 'Position', [80 80 1440 900], ...
    'NumberTitle', 'off');
ax = axes(fig, 'Color', [0.055 0.075 0.10], 'XColor', [0.82 0.87 0.92], ...
    'YColor', [0.82 0.87 0.92], 'ZColor', [0.82 0.87 0.92]);
hold(ax, 'on');
validIndices = find(axisEligible & lowVolEligible);
missingColorIndices = find(axisEligible & ~lowVolEligible);
colored = scatter3(ax, xyz(validIndices, 1), xyz(validIndices, 2), xyz(validIndices, 3), ...
    86, lowVol(validIndices), 'filled', 'MarkerEdgeColor', [0.82 0.90 0.96], ...
    'LineWidth', 0.6, 'UserData', validIndices);
grayPoints = scatter3(ax, xyz(missingColorIndices, 1), xyz(missingColorIndices, 2), ...
    xyz(missingColorIndices, 3), 86, [0.50 0.55 0.61], 'filled', ...
    'MarkerEdgeColor', [0.82 0.90 0.96], 'LineWidth', 0.6, ...
    'UserData', missingColorIndices);
grid(ax, 'on');
ax.GridColor = [0.28 0.36 0.45];
ax.GridAlpha = 0.42;
xlim(ax, [-3 3]); ylim(ax, [-3 3]); zlim(ax, [-3 3]);
xticks(ax, -3:1:3); yticks(ax, -3:1:3); zticks(ax, -3:1:3);
xlabel(ax, 'Value · higher = higher earnings/dividend yield', 'Color', [0.87 0.91 0.96]);
ylabel(ax, 'Momentum · 12-1 return and price vs MA200', 'Color', [0.87 0.91 0.96]);
zlabel(ax, 'Quality · ROE and inverse debt/equity', 'Color', [0.87 0.91 0.96]);
title(ax, { 'LQ45 Factor Zoo · descriptive cross-sectional scores', ...
    sprintf('Current snapshot · price as of %s · %d plotted issuers of 45', ...
    payload.as_of.price, sum(axisEligible)) }, 'Color', [0.91 0.94 0.98]);
cb = colorbar(ax);
colormap(ax, parula(256));
cb.Ticks = -3:1:3;
cb.Label.String = 'Low Volatility score · higher = lower beta/residual volatility';
cb.Color = [0.87 0.91 0.96];
clim(ax, [-3 3]);
if isempty(validIndices)
    legend(ax, grayPoints, {'Low Volatility unavailable/partial'}, 'TextColor', [0.87 0.91 0.96]);
elseif isempty(missingColorIndices)
    legend(ax, colored, {'Low Volatility score'}, 'TextColor', [0.87 0.91 0.96]);
else
    legend(ax, [colored grayPoints], {'Low Volatility score', 'Low Volatility unavailable/partial'}, ...
        'TextColor', [0.87 0.91 0.96], 'Location', 'northeastoutside');
end
hold(ax, 'off');
view(ax, [-37.5 28]);
rotate3d(fig, 'on');
zoom(fig, 'on');
dcm = datacursormode(fig);
dcm.Enable = 'on';
dcm.UpdateFcn = @(~, event) issuerTip(event, records);
savefig(fig, figurePath);

cameraTimer = timer('ExecutionMode', 'fixedSpacing', 'Period', 0.5, ...
    'BusyMode', 'drop', 'TimerFcn', @(~, ~) publishCamera(fig, ax, viewPath, payload.artifact_fingerprint));
setappdata(fig, 'factorZooCameraTimer', cameraTimer);
fig.CloseRequestFcn = @(source, ~) closeFactorZoo(source);
publishCamera(fig, ax, viewPath, payload.artifact_fingerprint);
start(cameraTimer);
end

function value = factorScore(record, factorName)
value = NaN;
if ~isfield(record, 'scores') || ~isfield(record.scores, factorName)
    return;
end
factor = record.scores.(factorName);
if isfield(factor, 'status') && strcmp(factor.status, 'AVAILABLE') && ...
        isfield(factor, 'score') && isnumeric(factor.score) && isscalar(factor.score) && isfinite(factor.score)
    value = double(factor.score);
end
end

function lines = issuerTip(event, records)
indices = event.Target.UserData;
rowIndex = indices(event.DataIndex);
record = records(rowIndex);
names = {'value', 'quality', 'momentum', 'low_volatility'};
factorLines = strings(1, numel(names) * 2);
for i = 1:numel(names)
    factor = record.scores.(names{i});
    if strcmp(factor.status, 'AVAILABLE') || strcmp(factor.status, 'PARTIAL')
        shown = sprintf('%.2f (%s)', factor.score, factor.status);
    else
        shown = sprintf('unavailable (%s)', factor.status);
    end
    componentNames = fieldnames(record.components);
    relevant = strings(1, 0);
    for j = 1:numel(componentNames)
        component = record.components.(componentNames{j});
        isRelevant = (strcmp(names{i}, 'value') && ismember(componentNames{j}, {'earnings_yield','dividend_yield'})) || ...
                     (strcmp(names{i}, 'quality') && ismember(componentNames{j}, {'roe','debt_to_equity'})) || ...
                     (strcmp(names{i}, 'momentum') && ismember(componentNames{j}, {'momentum_12_1','price_vs_ma200'})) || ...
                     (strcmp(names{i}, 'low_volatility') && ismember(componentNames{j}, {'beta_ihsg','idiosyncratic_volatility'}));
        if isRelevant
            if isfield(component, 'value') && isnumeric(component.value) && isscalar(component.value)
                componentText = sprintf('%s=%.4g', componentNames{j}, component.value);
            else
                componentText = sprintf('%s %s', componentNames{j}, component.status);
            end
            if isfield(component, 'reason') && ~isempty(component.reason)
                componentText = sprintf('%s (%s)', componentText, component.reason);
            end
            relevant(end + 1) = string(componentText); %#ok<AGROW>
        end
    end
    factorLines(2 * i - 1) = sprintf('%s score %s', names{i}, shown);
    factorLines(2 * i) = sprintf('  inputs: %s', char(strjoin(relevant, ', ')));
end
lines = {record.ticker, record.company, ...
    sprintf('Subsector: %s', record.sub_sector), ...
    sprintf('As of: %s', record.report_as_of), ...
    char(strjoin(factorLines, ' · '))};
end

function publishCamera(fig, ax, viewPath, fingerprint)
if ~isgraphics(fig) || ~isgraphics(ax)
    return;
end
angles = ax.View;
if isappdata(fig, 'factorZooLastCamera')
    previous = getappdata(fig, 'factorZooLastCamera');
    if max(abs(angles - previous)) < 0.05
        return;
    end
end
state = struct('schema_version', 'portfolio-factor-zoo.v1', ...
    'azimuth', angles(1), 'elevation', angles(2), ...
    'updated_at_utc', char(datetime('now', 'TimeZone', 'UTC', ...
    'Format', 'yyyy-MM-dd''T''HH:mm:ss.SSS''Z''')), ...
    'artifact_fingerprint', fingerprint);
encoded = jsonencode(state);
temporaryPath = [viewPath '.tmp'];
fileId = fopen(temporaryPath, 'w');
if fileId < 0
    warning('FactorZoo:CameraWrite', 'Unable to create temporary camera-state file.');
    return;
end
cleanup = onCleanup(@() fclose(fileId));
fwrite(fileId, encoded, 'char');
clear cleanup;
[ok, message] = movefile(temporaryPath, viewPath, 'f');
if ~ok
    warning('FactorZoo:CameraPublish', 'Camera-state publish failed: %s', message);
else
    setappdata(fig, 'factorZooLastCamera', angles);
end
end

function closeFactorZoo(fig)
if isappdata(fig, 'factorZooCameraTimer')
    cameraTimer = getappdata(fig, 'factorZooCameraTimer');
    if isvalid(cameraTimer)
        stop(cameraTimer);
        delete(cameraTimer);
    end
    rmappdata(fig, 'factorZooCameraTimer');
end
delete(fig);
end
