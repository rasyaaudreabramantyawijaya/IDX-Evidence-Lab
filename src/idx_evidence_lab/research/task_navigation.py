"""Allowlisted workspace plans; never execute model-generated code or market claims."""
import re

from .research_types import ResearchContext, ResearchPlan


def resolve_research_plan(query: str, previous: ResearchContext | None, known_tickers: list[str]) -> ResearchPlan:
    """Resolve local entities and bounded research categories without invented tickers."""
    allowed = {str(t).upper() for t in known_tickers}
    text = query.casefold()
    entities = sorted(t for t in allowed if re.search(rf'\b{re.escape(t)}\b', query, re.I))
    if 'bank central asia' in text and 'BBCA' in allowed and 'BBCA' not in entities:
        entities.append('BBCA')
    compare = bool(re.search(r'banding|compar|versus|\bvs\b', text))
    if compare and previous:
        entities = list(dict.fromkeys(previous.entities + entities))[:10]
    explicit = bool(entities)
    if not entities and previous:
        entities = previous.entities.copy()
    rules = [
        (r'risiko|volatil|drawdown|harga|price|return', 'price_risk'),
        (r'valuasi|undervalue|murah|valuat', 'valuation'),
        (r'fundamental|laba|pendapatan|utang|profit', 'fundamental'),
        (r'flow|broker|asing', 'flow'), (r'akuisisi|merger|dividen|hmetd|buyback|aksi korporasi', 'events'),
        (r'berita|news|artikel', 'news'), (r'hukum|aturan|pasal|pojk|regulasi', 'legal'),
        (r'ihsg|pasar|market|breadth', 'market'), (r'portofolio|portfolio|alokasi', 'portfolio'),
        (r'metode|konsep|apa itu|rumus', 'method'),
    ]
    categories = [category for pattern, category in rules if re.search(pattern, text)]
    if not categories:
        categories = [previous.topic if previous else 'fundamental' if entities else 'method']
    match = re.search(r'\b(\d{1,3})\s*(hari|minggu|bulan|tahun)\b', text)
    period = {'horizon': int(match[1]), 'unit': match[2]} if match else (
        previous.period.copy() if previous and (compare or not explicit) else {})
    scope = 'comparison' if len(entities) > 1 else 'issuer' if entities else (
        'portfolio' if 'portfolio' in categories else 'market' if 'market' in categories else 'concept')
    unknown = [t for t in re.findall(r'\b[A-Z]{4}\b', query) if t not in allowed and t not in {'IHSG', 'CAPM', 'ROIC', 'EBIT', 'LQ45'}]
    clarification = None
    if unknown:
        clarification = 'Ticker tersebut belum dikenali dalam universe lokal. Sebutkan emiten yang tersedia.'
    elif not entities and re.search(r'risikonya|sahamnya|emiten itu|perusahaan itu|kesimpulan itu', text):
        clarification = 'Emiten atau hasil lokal mana yang ingin dibahas?'
    return ResearchPlan(ResearchContext(entities, scope, categories[0], period), categories, clarification,
                        bool(re.search(r'forecast|prediksi|depan|peluang|probabil', text)),
                        bool(re.search(r'peluang|probabil|kemungkinan', text)), query)

PAGES = {'dashboard','issuer','screener','portfolio-lab','studies','news-universe','research','market','sources','watchlist','settings'}
WIDGETS = {'price_risk','trend_momentum','liquidity_proxy','portfolio_risk','quality_valuation','fragility','issuer_flow','event_timeline','market_context','market_breadth','capm_benchmark','factor_exposure','issuer_compare','event_outcomes','custom_engineering','evidence_trace'}
TOPICS = {
    'acquisition': ('akuisisi','acquisition','acquire','takeover','pengambilalihan','tender offer'),
    'merger': ('merger','penggabungan'), 'dividend': ('dividen','dividend'),
    'rights': ('hmetd','rights issue','right issue','penambahan modal'),
    'buyback': ('buyback','pembelian kembali'),
}
CAPABILITIES = {
    'policy': 'Enter executes one workspace plan, not a choice list. Bare ticker is local. No web search, invented data, arbitrary code, or automatic portfolio calculation. Missing news stays empty.',
    'workspaces': {
        'issuer': 'Bare ticker opens its company profile.',
        'screener': 'Discover stocks: low_volatility uses existing beta/residual-volatility characteristic; value uses complete relative earnings/dividend-yield scores, not intrinsic value.',
        'portfolio-lab': 'Prepare allocation form and mentioned tickers; no automatic optimizer/trade.',
        'studies': 'Prepare allowlisted feature-engineering panels; panel layout is not calculation or training.',
        'news-universe': 'Filter ticker and topic; group matching local articles by mentioned issuer; no match means unavailable.',
        'research': 'Prepare the full research question; compose only from approved public excerpts.',
        'sources': 'Local provenance and legal references; private PDFs are never sent.',
        'market': 'IHSG, breadth, sector and market context.',
    },
    'widgets': sorted(WIDGETS), 'news_topics': list(TOPICS),
    'screen_modes': ['low_volatility','value',''],
    'requested_behavior': 'Pertanyaan risiko/feature engineering menyiapkan Studies; alokasi menyiapkan Portfolio Lab; berita BBCA/acquisition dikelompokkan per emiten. Jangan mengganti hasil kosong dengan artikel lain.',
}


def build_navigation(query, known_tickers, model_plan=None):
    text=query.casefold(); allowed={str(t).upper() for t in known_tickers}
    tickers=sorted(t for t in allowed if re.search(rf'\b{re.escape(t.casefold())}\b',text))
    if not tickers and re.search(r'\bbca\b|bank central asia',text) and 'BBCA' in allowed: tickers=['BBCA']
    topic=next((name for name,words in TOPICS.items() if any(w in text for w in words)),'')
    mode=''; widgets=[]
    if query.strip().upper() in allowed: page='issuer'
    elif re.search(r'stud(?:y|ies|i)|feature engineering|rekayasa fitur|bandingkan|compare',text): page='studies'
    elif re.search(r'berita|news|artikel|kabar',text): page='news-universe'
    elif re.search(r'alokasi|allocat|portofolio|portfolio',text): page='portfolio-lab'
    elif re.search(r'volatil+itas? rendah|volatilitas rendah|low.vol|undervalue|murah|valuasi rendah|screener|filter saham|cari saham',text): page='screener'
    elif re.search(r'aturan|pasal|pojk|regulasi|sumber|metode pdf',text): page='sources'
    elif re.search(r'ihsg|kondisi pasar|market overview|breadth|heatmap',text): page='market'
    elif re.search(r'risiko|volatil|momentum|rsi|drawdown|faktor|capm',text): page='studies'
    else: page='research'
    if page=='screener':
        mode='low_volatility' if re.search(r'volatil|low.vol|risiko rendah',text) else 'value' if re.search(r'undervalue|murah|valuasi',text) else ''
    groups=[(r'volatil|risiko|drawdown|atr','price_risk'),(r'momentum|rsi|macd|trend','trend_momentum'),(r'valu|murah|quality|fundamental','quality_valuation'),(r'berita|akuisisi|merger|event','event_timeline'),(r'flow|broker|asing','issuer_flow'),(r'capm|beta','capm_benchmark'),(r'faktor|factor','factor_exposure'),(r'banding|compare','issuer_compare'),(r'feature engineering|fitur sendiri','custom_engineering')]
    widgets=[name for pattern,name in groups if re.search(pattern,text)]
    if page=='studies' and not widgets: widgets=['price_risk','quality_valuation']
    plan=model_plan if isinstance(model_plan,dict) else {}
    # A bare ticker cannot be redirected by a model. Fields are closed enums.
    if query.strip().upper() not in allowed and isinstance(plan.get('page'),str) and plan['page'] in PAGES: page=plan['page']
    candidates=plan.get('tickers',[])
    if isinstance(candidates,list):
        inferred=[t.upper() for t in candidates if isinstance(t,str) and t.upper() in allowed]
        if inferred: tickers=list(dict.fromkeys(tickers+inferred))[:10]
    if isinstance(plan.get('screen_mode'),str) and plan['screen_mode'] in {'low_volatility','value'}: mode=plan['screen_mode']
    if isinstance(plan.get('news_topic'),str) and plan['news_topic'] in TOPICS: topic=plan['news_topic']
    candidates=plan.get('widgets',[])
    if isinstance(candidates,list):
        selected=[w for w in candidates if isinstance(w,str) and w in WIDGETS]
        if selected: widgets=list(dict.fromkeys(selected))[:8]
    if page=='studies' and 'evidence_trace' not in widgets: widgets.append('evidence_trace')
    return {'page':page,'tickers':tickers,'screen_mode':mode if page=='screener' else '',
            'news_topic':topic if page=='news-universe' else '',
            'widgets':widgets if page=='studies' else [],'query':query[:500]}
