"""Portfolio Lab navigation and client contract smoke checks."""

from pathlib import Path

from idx_evidence_lab import web_app
from legacy_source import LEGACY_PAGE


HTML = LEGACY_PAGE


def test_portfolio_lab_has_own_destination_and_preserves_existing_pages():
    source = HTML.read_text(encoding="utf-8")
    assert 'data-page="portfolio-lab"' in source
    assert 'data-page="market"' in source
    assert 'data-page="research"' in source
    assert "'portfolio-lab':renderPortfolioLab" in source


def test_portfolio_lab_renders_accessible_controls_and_local_api_contract():
    source = HTML.read_text(encoding="utf-8")
    for behavior in ("function renderPortfolioLab()", "async function loadPortfolioData()",
                     "async function runPortfolioAnalysis(formState)",
                     "portfolioApiUrl('/api/portfolio-data')", "portfolioApiUrl('/api/portfolio-analysis')",
                     "aria-label=\"Cari emiten LQ45\"", "data-portfolio-ticker",
                     "portfolio-profile", "Metode & asumsi"):
        assert behavior in source
    for obsolete_control in ('Metode konstruksi<select', 'Sampel estimasi<select', 'Benchmark<select',
                             'data-portfolio-field="method"', 'data-portfolio-field="lookback"',
                             'data-portfolio-field="benchmark"'):
        assert obsolete_control not in source
    assert "requestGeneration" in source


def test_portfolio_catalog_failure_is_visible_and_retryable():
    source = HTML.read_text(encoding="utf-8")
    assert "Gagal memuat daftar LQ45" in source
    assert "data-action=\"portfolio-retry-catalog\"" in source
    assert "portfolioState.catalogAttempted=false" in source
    assert "IDX Evidence Lab: Local API (5501)" in source
    assert "localApiFailureMessage('/api/portfolio-data',error)" in source
    assert "<summary>Metode & asumsi</summary>" in source
    assert "Black–Litterman memakai prior kapitalisasi" in source


def test_portfolio_lab_separates_observation_simulation_and_missing_models():
    source = HTML.read_text(encoding="utf-8")
    for label in ("Riwayat walk-forward", "Skenario eksploratoris", "Sharpe",
                  "Sortino", "Calmar", "Maximum drawdown", "CAPM",
                  "Black–Litterman", "Fama–French", "APT", "belum tersedia",
                  "bukan tanggal pasti", "tidak mengirim order"):
        assert label in source
    assert "function portfolioFanChart" in source
    assert "function portfolioWeightsChart" in source


def test_capm_explains_unavailable_market_premium_without_fabricating_hurdle():
    source = HTML.read_text(encoding="utf-8")
    assert "function capmExplainer" in source
    assert "Rₘ − Rf" in source
    assert "Premi pasar belum tersedia" in source
    assert "CAPM · asumsi pemulihan ATH IHSG" in source
    assert "Rₘ asumsi pemulihan IHSG ke ATH" in source
    assert "hurdle CAPM yang dihasilkan adalah ambang heuristik" in source
    assert "penutupan lokal" in source
    assert "athSnapshot?.ath_recovery_as_of" in source


def test_ath_scenario_and_historical_capm_render_as_separate_windows():
    source = HTML.read_text(encoding="utf-8")
    assert "function historicalCapmPanel" in source
    assert "CAPM · historis IHSG" in source
    assert "CAPM · asumsi pemulihan ATH IHSG" in source
    assert "historical_capm" in source
    assert 'term(\'beta\',\'β portofolio vs benchmark\'' in source
    assert 'term(\'risk-free\',\'Rf · input manual p.a.\'' in source
    assert 'term(\'market-premium\'' in source
    assert "capmExplainer(m.beta,m.assumptions?.risk_free_annual,m.assumptions?.market_premium_annual,m.capm_hurdle)" in source


def test_simulated_drawdown_quantile_visual_is_honest_and_zero_anchored():
    source = HTML.read_text(encoding="utf-8")
    assert "Rentang maximum drawdown prediktif" in source
    assert "function gbmForecastPanel" in source and "Uji out-of-sample" in source
    assert "p10–median–p90" in source
    assert "Distribusi maximum drawdown" not in source
    assert 'scenario-mdd-track' in source
    assert '0% · batas sumbu' in source
    assert 'bukan hasil maximum drawdown portofolio' in source


def test_portfolio_risk_ratios_and_maximum_drawdown_have_explanatory_visuals():
    source = HTML.read_text(encoding="utf-8")
    for visual in ("function sortinoDownsideChart", "function ratioComponentsChart",
                   "function drawdownPathChart", "Area downside di bawah target",
                   "Puncak", "Lembah", "Pulih"):
        assert visual in source
    assert "sortinoDownsideChart(m.path,m.assumptions?.target_daily,m.assumptions?.target_annual)" in source
    assert "ratioComponentsChart('Sharpe'" in source
    assert "ratioComponentsChart('Calmar'" in source
    assert "<summary>Lihat baseline dan metode pembanding</summary>" in source
    assert "grid-template-columns:repeat(2,minmax(0,1fr))" in source
    assert "class=\"portfolio-risk-zero\"" in source
    assert "Skala simetris per kartu" in source
    assert "aria-label=\"Distribusi kepadatan" in source
    assert "Target minimum" in source
    assert "CAGR dibanding |maximum drawdown|" in source
    assert "Belum pulih dalam sampel" in source
    assert "Risk-free manual ${(rf*100).toFixed(3)}% p.a. · asumsi pengguna, bukan feed ID10Y." in source


def test_sharpe_and_calmar_show_hoverable_expanding_historical_series():
    source = HTML.read_text(encoding="utf-8")
    assert "function expandingRatioChart(path,kind,riskFreeAnnual)" in source
    assert "expandingRatioChart(m.path,'sharpe',rf)" in source
    assert "expandingRatioChart(m.path,'calmar')" in source
    assert "data-chart-interaction" in source
    assert "data-chart-point" in source
    assert "minimal 20 sesi" in source
    assert "Ekspanding dari awal sampel" in source


def test_portfolio_factor_exposures_have_zero_centered_visual_scale_and_coverage():
    source = HTML.read_text(encoding="utf-8")
    assert ".factor-zoo-exposure-track" in source
    assert "factor-zoo-exposure-zero" in source
    assert "factor-zoo-exposure-fill" in source
    assert 'role="img" aria-label="Eksposur ${labels[factor]}:' in source
    assert "scoreValue==null?'tidak tersedia':factorScoreLabel(scoreValue)+'σ'" in source
    assert 'class="factor-zoo-exposure-scale" aria-hidden="true"><span>−3σ</span><span>0σ</span><span>+3σ</span>' in source
    assert "Cakupan bobot ${factorValueLabel(covered*100)}%" in source
    assert "bukan attribution return" in source


def test_portfolio_lab_has_weighted_subsector_circle_composition():
    source = HTML.read_text(encoding="utf-8")
    api_source = (Path(web_app.__file__).parent / "portfolio" / "portfolio_service.py").read_text(encoding="utf-8")
    assert '"sub_sectors": inputs["sub_sectors"]' in api_source
    assert "function portfolioSubsectorBubbles" in source
    assert "portfolioSubsectorBubbles(portfolioState.result.allocation,portfolioState.result.sub_sectors" in source
    assert "data-subsector" in source
    assert "Komposisi per subsektor · lingkaran emiten" in source
    assert "Diameter lingkaran mengikuti akar bobot alokasi" in source
    assert "mountPortfolioCapitalField" in source
    assert "Total modal (Rp, opsional)" in source
    assert "total_capital:formState.capital===''?null:Number(formState.capital)" in source


def test_portfolio_lab_has_no_dummy_ratio_or_auto_trade_controls():
    source = HTML.read_text(encoding="utf-8")
    start = source.index("function renderPortfolioLab()")
    end = source.index("function ", start + len("function renderPortfolioLab()"))
    panel = source[start:end]
    assert "p.result?portfolioResults()" in panel
    assert "1.25 Sharpe" not in panel
    assert "automatic-trade" not in source


def test_portfolio_lab_invalidates_stale_result_and_does_not_retry_catalog_forever():
    source = HTML.read_text(encoding="utf-8")
    assert "function invalidatePortfolioResult()" in source
    assert "portfolioState.catalogAttempted" in source
    assert "requestGeneration!==portfolioState.requestGeneration" in source


def test_portfolio_analysis_network_failure_explains_local_api_recovery():
    source = HTML.read_text(encoding="utf-8")
    assert "localApiFailureMessage('/api/portfolio-analysis',error)" in source
    assert "portfolioState.error=localApiFailureMessage" in source


def test_portfolio_percentage_does_not_render_missing_value_as_zero():
    source = HTML.read_text(encoding="utf-8")
    assert "function portfolioPct(value,digits=1){return value==null||value===''?'—'" in source
