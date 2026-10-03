"""Structural/source/numeric guards, not a guarantee of semantic correctness."""
from decimal import Decimal, InvalidOperation
import re
from .research_types import AnswerBlock, CLAIMS, ResearchReply

NUMBERS = re.compile(r'(?<![\w])[-+]?\d+(?:[.,]\d+)*(?:\s*(?:%|pp))?(?![\w])')
DATES = re.compile(r'\b\d{4}-\d{2}-\d{2}\b')
FORECAST_FIELDS = {'target', 'horizon', 'input_cutoff', 'method_version', 'baseline', 'diagnostics', 'validation_status'}


def _decimal(display):
    text = display.strip().replace(' ', '')
    if ',' in text:
        text = text.replace('.', '').replace(',', '.')
    return Decimal(text)


def _display_valid(display, metric):
    text = display.strip()
    try:
        if text.endswith('pp'):
            return metric.unit == 'pp' and _decimal(text[:-2]) == Decimal(str(metric.value))
        if text.endswith('%'):
            return metric.unit in {'fraction', 'fraction/year', 'fraction/day', 'percent'} and _decimal(text[:-1]) == (
                Decimal(str(metric.value)) * 100 if metric.unit.startswith('fraction') else Decimal(str(metric.value)))
        return _decimal(text) == Decimal(str(metric.value))
    except (InvalidOperation, ValueError):
        return False


def validate_research_reply(raw, pack, context):
    if not isinstance(raw, dict) or not isinstance(raw.get('blocks'), list) or not 1 <= len(raw['blocks']) <= 20:
        raise ValueError('INVALID_FORMAT')
    evidence = {i.id: i for i in pack.items}
    metrics = {m.id: m for m in pack.metrics}
    blocks = []
    for value in raw['blocks']:
        if not isinstance(value, dict):
            raise ValueError('INVALID_FORMAT')
        try:
            block = AnswerBlock(**value)
        except TypeError as exc:
            raise ValueError('INVALID_FORMAT') from exc
        if block.kind not in {'text', 'table'} or block.claim_kind not in CLAIMS or not isinstance(block.text, str):
            raise ValueError('INVALID_FORMAT')
        if not all(isinstance(ids, list) and all(isinstance(i, str) for i in ids) for ids in [block.evidence_ids, block.metric_ids]):
            raise ValueError('INVALID_FORMAT')
        if any(i not in evidence for i in block.evidence_ids) or any(i not in metrics for i in block.metric_ids):
            raise ValueError('INVALID_EVIDENCE')
        if block.claim_kind != 'concept' and not (block.evidence_ids or block.metric_ids):
            raise ValueError('MISSING_EVIDENCE')
        if block.claim_kind in {'forecast', 'predictive_probability'}:
            selected = [metrics[i] for i in block.metric_ids]
            if not selected or any(m.claim_kind != block.claim_kind or not m.forecast_metadata or
                not all(m.forecast_metadata.get(f) for f in FORECAST_FIELDS) for m in selected):
                raise ValueError('UNSUPPORTED_FORECAST')
        if not isinstance(block.columns, list) or any(not isinstance(c, str) for c in block.columns) or not isinstance(block.rows, list):
            raise ValueError('INVALID_TABLE')
        if any(not isinstance(row, list) or len(row) != len(block.columns) or any(not isinstance(c, str) for c in row) for row in block.rows):
            raise ValueError('INVALID_TABLE')
        text = '\n'.join([block.text, *block.columns, *(c for row in block.rows for c in row)])
        if len(text) > 24000 or re.search(r'<[^>]+>|!\[|data:image|https?://', text, re.I):
            raise ValueError('NON_TEXT_OUTPUT')
        remaining = text
        valid_dates = {d for i in block.evidence_ids for d in DATES.findall(evidence[i].excerpt)}
        valid_dates.update(d for i in block.metric_ids for d in DATES.findall(str(metrics[i].period)))
        for date in DATES.findall(text):
            if date not in valid_dates:
                raise ValueError('UNSUPPORTED_DATE')
            remaining = remaining.replace(date, '')
        if not isinstance(block.numeric_claims, list):
            raise ValueError('INVALID_FORMAT')
        for claim in block.numeric_claims:
            if not isinstance(claim, dict) or not isinstance(claim.get('display'), str):
                raise ValueError('INVALID_NUMBER')
            id = claim.get('metric_id')
            if id not in block.metric_ids or claim.get('value') != metrics[id].value or claim.get('unit') != metrics[id].unit or not _display_valid(claim['display'], metrics[id]):
                raise ValueError('INVALID_NUMBER')
            # Match a complete displayed number, never erase digits inside another value.
            remaining = re.sub(r'(?<![\w])(?<!\d[.,])' + re.escape(claim['display']) + r'(?![\w%]|[.,]\d)', '', remaining)
        for token in NUMBERS.findall(remaining):
            # Source-quoted numbers retain reported-number status. They cannot substantiate forecasts.
            if block.claim_kind != 'observation' or not any(token in NUMBERS.findall(evidence[i].excerpt) for i in block.evidence_ids):
                raise ValueError('UNSUPPORTED_NUMBER')
        blocks.append(block)
    return ResearchReply('MODEL_INFERENCE', blocks, pack.items, pack.metrics, pack.coverage, pack.missing_inputs,
                         {'provider': 'OpenRouter', 'status': 'GENERATED', 'semantic_validation': 'NOT_GUARANTEED'}, context)


def compose_local_reply(plan, pack):
    blocks = []
    missing = pack.missing_inputs.copy()
    if plan.clarification:
        blocks.append(AnswerBlock(text=plan.clarification))
        status = 'CLARIFICATION_REQUIRED'
    else:
        status = 'LOCAL_EVIDENCE' if pack.items or pack.metrics else 'INSUFFICIENT_EVIDENCE'
        if not pack.items and not pack.metrics:
            blocks.append(AnswerBlock(text='Belum ditemukan bukti atau hasil perhitungan lokal yang relevan. Ini tidak membuktikan kejadian tersebut tidak terjadi.'))
        for metric in pack.metrics:
            blocks.append(AnswerBlock(claim_kind=metric.claim_kind,
                text=f'{", ".join(metric.entities)} — {metric.name}: {metric.value} {metric.unit}. Periode: {metric.period}. Status: {metric.validation_status}. ' + ' '.join(metric.limits),
                metric_ids=[metric.id]))
        for item in pack.items:
            blocks.append(AnswerBlock(claim_kind='observation', text=item.excerpt, evidence_ids=[item.id]))
        if plan.wants_forecast or plan.wants_probability:
            kind = 'predictive_probability' if plan.wants_probability else 'forecast'
            if not any(m.claim_kind == kind and m.forecast_metadata for m in pack.metrics):
                missing.append('Metode prediktif dengan target, horizon, cutoff dan diagnostik belum tersedia.')
                blocks.append(AnswerBlock(text='Estimasi numerik belum dapat diberikan: belum ada artefak metode prediktif yang sesuai. Frekuensi historis dan analog tidak otomatis menjadi peluang masa depan. Skenario kualitatif hanya dapat dibahas berdasarkan bukti lokal dan asumsi eksplisit.'))
        blocks.append(AnswerBlock(text='Batas interpretasi: arsip lokal bukan data live; kecocokan sumber tidak membuktikan sebab-akibat atau niat. Periksa periode, kualitas input, alternatif penjelasan, dan bukti yang dapat membatalkan kesimpulan.'))
    return ResearchReply(status, blocks, pack.items, pack.metrics, pack.coverage, missing,
                         {'provider': 'local', 'status': 'NOT_REQUESTED'}, plan.context)
