%% IHSG historical tail-loss surface for the Market Overview prototype
% Local-only MATLAB rendering. No network calls are made.
% X = month-end as-of date, each point based on the trailing 252 daily returns.
% Y = empirical loss quantile; Z = observed historical loss quantile (%).
% This is an empirical EVT-context diagnostic, not an extrapolated EVT model.

scriptPath = mfilename('fullpath');
projectRoot = fileparts(fileparts(scriptPath));
snapshotPath = fullfile(projectRoot, 'docs', 'prototypes', 'market-overview-data.json');
outputStem = fullfile(projectRoot, 'docs', 'prototypes', 'ihsg-evt-tail-surface');

if ~isfile(snapshotPath)
    error('IDXEL:MissingSnapshot', 'Local snapshot not found: %s', snapshotPath);
end

snapshot = jsondecode(fileread(snapshotPath));
if ~isfield(snapshot, 'ihsg') || ~snapshot.ihsg.ok || ~isfield(snapshot.ihsg, 'series')
    error('IDXEL:InvalidSnapshot', 'Snapshot does not contain a usable IHSG series.');
end

ihsg = snapshot.ihsg;
series = ihsg.series;
dates = datetime(string({series.date}), 'InputFormat', 'yyyy-MM-dd');
prices = double([series.price]);
[dates, order] = sort(dates(:));
prices = prices(order(:));

if numel(unique(dates)) ~= numel(dates) || any(~isfinite(prices)) || any(prices <= 0)
    error('IDXEL:QualityGuard', 'Dates must be unique and prices finite and positive.');
end

returns = diff(log(prices));
losses = -returns;
returnDates = dates(2:end);
lookbackSessions = 252;
tailLevels = [0.90 0.925 0.95 0.975];

% Select the last completed observation in each calendar month, then retain
% up to 24 month-ends for a readable, reproducible historical surface.
monthKeys = year(returnDates) * 100 + month(returnDates);
[~, ~, monthGroup] = unique(monthKeys, 'stable');
monthEndIndices = accumarray(monthGroup, (1:numel(monthGroup))', [], @max);
monthEndIndices = monthEndIndices(max(1, end-23):end);
monthEndIndices = monthEndIndices(monthEndIndices >= lookbackSessions);
asOfDates = returnDates(monthEndIndices);

if numel(asOfDates) < 6
    error('IDXEL:InsufficientHistory', 'At least six month-end windows with 252 returns are required.');
end

Z = nan(numel(tailLevels), numel(asOfDates));
for j = 1:numel(asOfDates)
    windowLosses = sort(losses(monthEndIndices(j)-lookbackSessions+1:monthEndIndices(j)));
    n = numel(windowLosses);
    for i = 1:numel(tailLevels)
        % Linear empirical quantile interpolation, equivalent to the common
        % (n-1)*p convention, implemented without a toolbox dependency.
        position = 1 + (n - 1) * tailLevels(i);
        lo = floor(position);
        hi = ceil(position);
        fraction = position - lo;
        lossQuantile = windowLosses(lo) + fraction * (windowLosses(hi) - windowLosses(lo));
        Z(i, j) = 100 * lossQuantile;
    end
end

% Render the native MATLAB figure and save both the editable .fig and a
% high-resolution static image consumed by the local HTML prototype.
fig = figure('Color', [0.035 0.060 0.095], 'Position', [120 120 1500 900], ...
    'Name', 'IHSG Historical Tail-Loss Surface', 'NumberTitle', 'off');
ax = axes(fig, 'Color', [0.035 0.060 0.095], 'XColor', [0.78 0.84 0.91], ...
    'YColor', [0.78 0.84 0.91], 'ZColor', [0.78 0.84 0.91], ...
    'GridColor', [0.40 0.52 0.66], 'GridAlpha', 0.22, 'LineWidth', 0.8);
[X, Y] = meshgrid(1:numel(asOfDates), 100*tailLevels);
surfaceHandle = surf(ax, X, Y, Z, Z, 'FaceColor', 'interp', ...
    'EdgeColor', [0.28 0.65 0.78], 'EdgeAlpha', 0.48, 'LineWidth', 0.8);
hold(ax, 'on');
contour3(ax, X, Y, Z, 7, 'LineColor', [0.78 0.86 0.94], 'LineWidth', 0.65);
hold(ax, 'off');
colormap(ax, turbo(256));
cb = colorbar(ax);
cb.Color = [0.78 0.84 0.91];
cb.Label.String = 'Empirical downside loss (%)';
cb.Label.Color = [0.88 0.92 0.97];
ax.XLim = [0.5 numel(asOfDates)+0.5];
ax.YLim = [89.5 98];
ax.ZLabel.String = 'Trailing-window loss quantile (%)';
ax.YLabel.String = 'Empirical loss quantile';
ax.XLabel.String = 'Month-end snapshot (each estimate uses prior 252 sessions)';
ax.XTick = unique(round(linspace(1, numel(asOfDates), min(8, numel(asOfDates)))));
ax.XTickLabel = cellstr(string(asOfDates(ax.XTick), 'MMM yyyy'));
ax.YTick = 100*tailLevels;
ax.YTickLabel = compose('%.1f%%', 100*tailLevels);
ax.ZLim = [min(0, floor(min(Z(:)))) ceil(max(Z(:))*1.12)];
ax.ZLabel.String = 'Observed loss threshold (%)';
ax.View = [43 29];
grid(ax, 'on');
box(ax, 'on');
title(ax, {'IHSG · Historical Tail-Loss Surface', ...
    sprintf('Sectors.app daily snapshot · %d returns · %s to %s · rolling %d-session windows', ...
    numel(losses), string(asOfDates(1), 'yyyy-MM-dd'), string(asOfDates(end), 'yyyy-MM-dd'), lookbackSessions)}, ...
    'Color', [0.91 0.95 0.99], 'FontWeight', 'bold');
subtitle(ax, 'Empirical p90–p97.5 loss quantiles; descriptive surface, not a crash probability or forecast', ...
    'Color', [0.64 0.73 0.83]);
rotate3d(fig, 'on');
set(surfaceHandle, 'ButtonDownFcn', @(~,~) rotate3d(fig, 'on'));

savefig(fig, string(outputStem) + ".fig");
exportgraphics(fig, string(outputStem) + ".png", 'Resolution', 180, 'BackgroundColor', [0.035 0.060 0.095]);

payload = struct();
payload.ok = true;
payload.title = 'IHSG Historical Tail-Loss Surface';
payload.method = 'Empirical rolling loss quantiles';
payload.data_quality = string(ihsg.data_quality);
payload.endpoint = string(ihsg.endpoint);
payload.observation_count = numel(prices);
payload.return_count = numel(losses);
payload.source_coverage_start = string(ihsg.coverage_start);
payload.source_coverage_end = string(ihsg.coverage_end);
payload.source_retrieved_at = string(ihsg.retrieved_at);
payload.generated_at_utc = string(datetime('now', 'TimeZone', 'UTC', ...
    'Format', "yyyy-MM-dd'T'HH:mm:ss.SSSXXX"));
payload.lookback_sessions = lookbackSessions;
payload.tail_levels = tailLevels;
payload.as_of_dates = string(asOfDates, 'yyyy-MM-dd');
payload.loss_quantiles_pct = Z;
payload.view_state = struct('azimuth', ax.View(1), 'elevation', ax.View(2), ...
    'updated_at_utc', payload.generated_at_utc);
payload.interpretation = 'Each surface point is the empirical quantile of negative close-to-close log returns over the trailing 252 sessions ending at the indicated month-end. No future return or extrapolated probability is represented.';
outputDataPath = string(outputStem) + "-data.json";
temporaryDataPath = outputDataPath + ".tmp";
fid = fopen(temporaryDataPath, 'w');
if fid < 0
    error('IDXEL:OutputWriteFailed', 'Could not create surface data JSON.');
end
cleanup = onCleanup(@() fclose(fid));
fwrite(fid, jsonencode(payload), 'char');
clear cleanup;
[moveOK, moveMessage] = movefile(temporaryDataPath, outputDataPath, 'f');
if ~moveOK
    error('IDXEL:OutputPublishFailed', 'Could not publish surface JSON: %s', moveMessage);
end

fprintf('MATLAB EVT-context surface generated.\n');
fprintf('Source: %s\n', snapshotPath);
fprintf('Surface grid: %d month ends × %d tail quantiles; lookback=%d sessions.\n', ...
    numel(asOfDates), numel(tailLevels), lookbackSessions);
fprintf('Outputs: %s.png, %s.fig, %s-data.json\n', outputStem, outputStem, outputStem);
if exist('idxelEvtViewSyncTimer', 'var') && isa(idxelEvtViewSyncTimer, 'timer') && isvalid(idxelEvtViewSyncTimer)
    stop(idxelEvtViewSyncTimer);
    delete(idxelEvtViewSyncTimer);
end
idxelEvtViewSyncTimer = timer('ExecutionMode', 'fixedSpacing', 'Period', 0.5, ...
    'BusyMode', 'drop', 'TimerFcn', ...
    @(timerObj, eventData) syncIhsgEvtSurfaceView(timerObj, ax, outputDataPath, payload));
start(idxelEvtViewSyncTimer);
fprintf('MATLAB view sync active: browser polls the shared JSON every 2.5 seconds.\n');

function syncIhsgEvtSurfaceView(timerObj, ax, outputDataPath, payload)
    persistent lastCameraView
    if ~isgraphics(ax)
        stop(timerObj);
        delete(timerObj);
        return;
    end
    camera = ax.View;
    if ~isempty(lastCameraView) && all(abs(camera - lastCameraView) < 0.05)
        return;
    end
    lastCameraView = camera;
    nowUtc = datetime('now', 'TimeZone', 'UTC');
    payload.view_state = struct('azimuth', camera(1), 'elevation', camera(2), ...
        'updated_at_utc', string(datetime(nowUtc, ...
        'Format', "yyyy-MM-dd'T'HH:mm:ss.SSSXXX")));
    payload.generated_at_utc = payload.view_state.updated_at_utc;
    temporaryDataPath = outputDataPath + ".tmp";
    fid = fopen(temporaryDataPath, 'w');
    if fid < 0
        return;
    end
    cleanup = onCleanup(@() fclose(fid));
    fwrite(fid, jsonencode(payload), 'char');
    clear cleanup;
    movefile(temporaryDataPath, outputDataPath, 'f');
end
