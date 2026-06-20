import hashlib
import json
import os
import ssl
import uuid
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, date

import pg8000.dbapi

# Auth — prefer APP_PASSWORD from env, but fall back to Ratul's chosen code.
PASSWORD = os.environ.get("APP_PASSWORD", "ratul2026")
VALID_TOKEN = ("jt-" + hashlib.sha256(("v1:" + PASSWORD).encode()).hexdigest()[:40]) if PASSWORD else ""

# Database (Neon Postgres). DATABASE_URL = postgresql://user:pass@host/db?sslmode=require
DATABASE_URL = os.environ.get("DATABASE_URL", "")
_conn = None

# Columns owned by the app (search_blob is a generated column, never written directly).
JOB_COLUMNS = [
    "id", "company", "role", "tier", "category", "url", "careers_url",
    "salary_range", "location", "status", "notes", "description", "source",
    "date_added", "date_applied", "priority", "deadline",
]
DATE_FIELDS = {"date_added", "date_applied", "deadline"}


def _parse_dsn(url):
    p = urlparse(url)
    return dict(
        user=p.username,
        password=p.password,
        host=p.hostname,
        port=p.port or 5432,
        database=(p.path or "/").lstrip("/") or "neondb",
    )


def get_conn():
    """Cached connection, revalidated per request (Neon pooled endpoint)."""
    global _conn
    if _conn is not None:
        try:
            c = _conn.cursor()
            c.execute("SELECT 1")
            c.close()
            return _conn
        except Exception:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None
    ctx = ssl.create_default_context()
    _conn = pg8000.dbapi.connect(ssl_context=ctx, **_parse_dsn(DATABASE_URL))
    _conn.autocommit = True
    return _conn


def _iso(v):
    if isinstance(v, (date, datetime)):
        return v.isoformat()[:10]
    return v


def _date_or_none(v):
    v = v.strip() if isinstance(v, str) else v
    return v if v else None


def row_to_job(row):
    job = {}
    for k, v in zip(JOB_COLUMNS, row):
        job[k] = _iso(v) if k in DATE_FIELDS else v
    return job
ARCHIVE_STATUSES = {"expired", "not_interested", "rejected", "withdrawn"}
AUTO_KEYWORDS = [
    'automation', 'zapier', 'airtable', 'no-code', 'nocode', 'integration', 'crm', 'api',
    'make.com', 'n8n', 'smartlead', 'clay', 'revops', 'revenue operations', 'sales ops',
    'gtm ops', 'workflow'
]
EARLY_GOOD = [
    'early career', 'early careers', 'new grad', 'new graduate', 'graduate program', 'campus',
    'intern', 'entry level', 'analyst', 'associate', 'coordinator', 'specialist', 'trainee', 'rotational'
]
EARLY_BAD = [
    '5+ year', '5 years', '6+ year', '7+ year', '8+ year', '10+ year', 'senior manager',
    'director', 'vice president', 'vp ', 'principal', 'partner', 'cpa required', 'isda', 'trioptima'
]
CFA_KEYWORDS = [
    'cfa', 'investment analy', 'portfolio', 'asset manage', 'wealth manage', 'fund account',
    'fund admin', 'valuation', 'financial analy', 'risk analy', 'model risk', 'credit risk',
    'fixed income', 'equity research', 'securities', 'capital market', 'corporate finance',
    'fp&a', 'financial plan', 'actuari', 'insurance analy', 'reits', 'real estate invest', 'cfa-qualifying'
]
FINANCE_FALL_GOOD = [
    'intern', 'internship', 'fall internship', 'fall 2026', 'autumn 2026', 'campus', 'new grad',
    'new graduate', 'analyst', 'associate', 'equity analyst', 'equity research', 'research analyst',
    'investment analyst', 'quant', 'quantitative', 'trading analyst', 'markets analyst', 'capital markets',
    'portfolio analyst', 'credit analyst', 'risk analyst', 'financial analyst'
]
FINANCE_FALL_DOMAIN = [
    'private equity', 'investment banking', 'equity research', 'asset management', 'wealth', 'pension',
    'capital markets', 'trading', 'quant', 'valuation', 'credit', 'portfolio', 'securities', 'investments',
    'corporate finance', 'financial modeling', 'fp&a', 'commercial finance', 'treasury'
]
FINANCE_FALL_BAD = [
    'senior ', 'director', 'vice president', 'vp ', 'principal', 'head of', 'chief ',
    '5+ year', '6+ year', '7+ year', '8+ year', '10+ year', 'manager,', 'manager -', 'manager –'
]
MICRO_MATURE_MARKERS = [
    'micro mature target', 'micro-mature target', 'micro mature', '1-10 employees', '1–10 employees',
    '5+ years old', 'at least 5 years old', '$5m+ revenue', '5m+ revenue', '5m revenue'
]
BOUTIQUE_HINTS = [
    'partners', 'capital', 'advisors', 'advisory', 'securities', 'wealth', 'ventures', 'equity', 'holdings'
]
TOP_TIER_FIRMS = [
    'rbc', 'td', 'bmo', 'scotiabank', 'cibc', 'national bank', 'brookfield', 'onex', 'otp',
    'ontario teachers', 'hoopp', 'cpp investments', 'cpb investments', 'omers', 'kpmg', 'deloitte',
    'pwc', 'ey', 'mckinsey', 'bcg', 'bain', 'goldman sachs', 'jpmorgan', 'morgan stanley', 'blackrock'
]
P_MAP = {"high": 0, "medium": 1, "low": 2}


_SELECT = "SELECT " + ", ".join(JOB_COLUMNS) + " FROM jobs"


def load_all_jobs():
    cur = get_conn().cursor()
    cur.execute(_SELECT)
    rows = cur.fetchall()
    cur.close()
    return {"jobs": [row_to_job(r) for r in rows]}


def get_job(job_id):
    cur = get_conn().cursor()
    cur.execute(_SELECT + " WHERE id = %s", (job_id,))
    row = cur.fetchone()
    cur.close()
    return row_to_job(row) if row else None


def build_meta(jobs):
    counts = {}
    categories = {}
    for job in jobs:
        status = job.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1
        category = (job.get("category") or "Other").strip()
        categories[category] = categories.get(category, 0) + 1
    active = [j for j in jobs if j.get("status") not in ARCHIVE_STATUSES]
    archived = [j for j in jobs if j.get("status") in ARCHIVE_STATUSES]
    return {
        "total": len(jobs),
        "active": len(active),
        "archived": len(archived),
        "counts": counts,
        "categories": dict(sorted(categories.items(), key=lambda kv: (-kv[1], kv[0].lower()))),
    }


def insert_job(job):
    cols = [c for c in JOB_COLUMNS]
    vals = [_date_or_none(job.get(c)) if c in DATE_FIELDS else job.get(c) for c in cols]
    sql = (
        "INSERT INTO jobs (" + ", ".join(cols) + ") VALUES ("
        + ", ".join(["%s"] * len(cols)) + ")"
    )
    cur = get_conn().cursor()
    cur.execute(sql, vals)
    cur.close()


def update_job(job_id, fields):
    if not fields:
        return
    sets, vals = [], []
    for k, v in fields.items():
        sets.append(f"{k} = %s")
        vals.append(_date_or_none(v) if k in DATE_FIELDS else v)
    sets.append("updated_at = now()")
    vals.append(job_id)
    cur = get_conn().cursor()
    cur.execute("UPDATE jobs SET " + ", ".join(sets) + " WHERE id = %s", vals)
    cur.close()


def delete_job(job_id):
    cur = get_conn().cursor()
    cur.execute("DELETE FROM jobs WHERE id = %s", (job_id,))
    rowcount = cur.rowcount
    cur.close()
    return rowcount > 0


def cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PATCH, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, X-Auth-Token",
        "Content-Type": "application/json"
    }


def _s(value):
    return "" if value is None else str(value)


def text_blob(job):
    return ((
        _s(job.get("role")) + " " +
        _s(job.get("category")) + " " +
        _s(job.get("company")) + " " +
        _s(job.get("notes")) + " " +
        _s(job.get("description")) + " " +
        _s(job.get("location"))
    )).lower()


def infer_firm_label(job):
    text = text_blob(job)
    company = _s(job.get('company')).lower()
    category = _s(job.get('category')).lower()
    if any(name in company for name in TOP_TIER_FIRMS):
        return 'Top Tier'
    if 'boutique' in text:
        return 'Boutique'
    if any(hint in company for hint in BOUTIQUE_HINTS):
        return 'Boutique'
    if any(k in text for k in ['pension', 'teachers', 'hoopp', 'cpp investments', 'cpb investments', 'omers']):
        return 'Institutional'
    if any(k in text for k in ['bank', 'banking', 'capital markets', 'securities']):
        return 'Large Firm'
    if any(k in category for k in ['private equity', 'investment banking', 'venture capital', 'capital markets', 'asset', 'wealth']):
        return 'Finance Firm'
    return 'Other'


def is_fall_finance_target(job):
    text = text_blob(job)
    if any(bad in text for bad in FINANCE_FALL_BAD):
        return False
    has_role_signal = any(good in text for good in FINANCE_FALL_GOOD)
    has_domain_signal = any(dom in text for dom in FINANCE_FALL_DOMAIN)
    if not (has_role_signal and has_domain_signal):
        return False
    status = job.get('status')
    if status in {'expired', 'withdrawn', 'rejected', 'not_interested'}:
        return False
    return True


def score_match(job):
    text = text_blob(job)
    lanes = {
        "Integrations": {
            "keywords": ['airtable', 'zapier', 'crm', 'hubspot', 'salesforce', 'integration', 'integrations', 'automation', 'workflow', 'api', 'implementation', 'onboarding', 'revops', 'revenue operations', 'sales ops', 'ops', 'support', 'technical support', 'customer success', 'solutions'],
            "titleBoost": ['specialist', 'coordinator', 'analyst', 'implementation', 'operations'],
        },
        "FPA": {
            "keywords": ['financial analyst', 'fp&a', 'forecasting', 'budgeting', 'cost analysis', 'pricing', 'p&l', 'variance', 'commercial finance', 'operational finance', 'reporting', 'excel', 'power bi', 'erp'],
            "titleBoost": ['analyst', 'finance', 'operations'],
        },
        "Data Analyst": {
            "keywords": ['data analyst', 'business analyst', 'analytics', 'dashboard', 'sql', 'python', 'tableau', 'power bi', 'etl', 'data pipeline', 'reporting', 'metrics', 'insights', 'product analytics'],
            "titleBoost": ['analyst', 'analytics', 'data'],
        },
        "PE": {
            "keywords": ['investment analyst', 'portfolio analytics', 'institutional investing', 'manager research', 'asset allocation', 'equity research', 'valuation', 'capital markets', 'cfa', 'investment consulting', 'wealth', 'pension', 'transaction advisory', 'corporate finance', 'underwriting', 'due diligence', 'acquisition', 'portfolio company', 'private markets', 'private capital', 'm&a', 'deals'],
            "titleBoost": ['analyst', 'associate', 'investment', 'financial analyst'],
        },
        "Consulting": {
            "keywords": ['consulting', 'strategy', 'business operations', 'project management', 'stakeholder', 'process improvement', 'cross-functional', 'operations analyst'],
            "titleBoost": ['analyst', 'associate', 'consulting'],
        }
    }
    negatives_hard = ['10+ year', '8+ year', '7+ year', '6+ year', '5-8 years', '5 to 8 years', 'director', 'vice president', 'vp ', 'principal', 'partner', 'cpa required', 'isda', 'csa', 'trioptima', 'numerix', 'markit', 'aladdin']
    negatives_medium = ['4+ year', '4 years', '5+ year', '5 years', 'senior manager', 'senior ', 'lead ', 'manager', 'derivatives middle office', 'quant developer', 'insurance product forms']
    context_bonus = ['entry level', 'new grad', 'new graduate', 'early career', 'analyst', 'associate', 'coordinator', 'specialist', 'toronto', 'waterloo', 'remote', 'hybrid', 'canada', 'startup', 'saas', 'fintech']
    interview_odds_bonus = ['airtable', 'zapier', 'clay', 'greenhouse', 'business systems', 'technical solutions', 'implementation', 'enablement', 'customer success', 'crm', 'revops', 'revenue operations', 'sales operations', 'workflow', 'api', 'webhook', 'dashboard', 'reporting', 'due diligence', 'underwriting', 'acquisition', 'screening', 'valuation', 'portfolio company', 'corporate finance', 'transaction advisory', 'deals', 'm&a', 'wealth management', 'asset management', 'private markets', 'private capital']
    interview_odds_penalty = ['staffing', 'recruiter', 'recruiting', 'contract', '12 month contract', '6 month contract', 'senior analyst', 'associate director', 'trading', 'quant', 'supervisory analyst']
    best_resume = 'General'
    best_score = -999
    reasons = []
    for resume, cfg in lanes.items():
        score = 0
        local_reasons = []
        for kw in cfg['keywords']:
            if kw in text:
                score += 4
                if len(local_reasons) < 3:
                    local_reasons.append(kw)
        for kw in cfg['titleBoost']:
            if kw in text:
                score += 2
        for kw in context_bonus:
            if kw in text:
                score += 1
        for kw in interview_odds_bonus:
            if kw in text:
                score += 2
        for kw in negatives_hard:
            if kw in text:
                score -= 8
        for kw in negatives_medium:
            if kw in text:
                score -= 4
        for kw in interview_odds_penalty:
            if kw in text:
                score -= 3
        if ((('asset management' in text) or ('private equity' in text) or ('equity research' in text) or ('portfolio' in text))
                and resume != 'PE' and not (('new grad' in text) or ('entry level' in text) or ('intern' in text))):
            score -= 3
        if any(k in text for k in ['startup', 'saas', 'fintech', 'healthtech', 'software', 'scale-up', 'scaleup', 'mid-sized', 'mid sized', 'small company', 'growing company', 'boutique', 'independent firm', 'wealth management firm', 'asset management firm', 'advisory firm', 'holding company', 'family office']):
            score += 3
        if 'toronto' in text:
            score += 2
        if any(k in text for k in ['posted today', 'posted 1 hour', 'posted 2 hours', 'posted 3 hours', 'posted 4 hours', 'posted 5 hours', 'posted 6 hours', 'posted 7 hours', 'posted 8 hours', 'posted 9 hours', 'posted 10 hours', 'posted 11 hours', 'posted 12 hours', 'posted 13 hours', 'posted 14 hours', 'posted 15 hours', 'posted 16 hours', 'posted 17 hours', 'posted 18 hours', 'posted 19 hours', 'posted 20 hours', 'posted 21 hours', 'posted 22 hours', 'posted 23 hours', 'posted within 24h', 'fresh linkedin posting']):
            score += 2
        status = job.get('status')
        if status == 'not_applied':
            score += 2
        elif status == 'saved':
            score += 1
        elif status in {'expired', 'withdrawn', 'rejected', 'not_interested'}:
            score -= 12
        if score > best_score:
            best_score = score
            best_resume = resume
            reasons = local_reasons
    final_score = max(best_score, 0)
    if final_score >= 22:
        chance = 'High Chance'
    elif final_score >= 14:
        chance = 'Strong Fit'
    elif final_score >= 8:
        chance = 'Reach'
    else:
        chance = 'Low ROI'
    return {
        'score': final_score,
        'bestResume': best_resume,
        'chance': chance,
        'reasons': reasons,
    }


def apply_filters(jobs, qs):
    status_filter = qs.get('status', [''])[0]
    category = qs.get('category', [''])[0]
    q = qs.get('q', [''])[0].strip().lower()
    tab = qs.get('tab', ['all'])[0]
    sort = qs.get('sort', ['date_added'])[0]
    sort_dir = qs.get('dir', [''])[0]
    qmode = qs.get('qmode', ['basic'])[0]
    exclude_terms = [t.strip().lower() for t in qs.get('exclude', [''])[0].split(',') if t.strip()]
    categories = [c for c in qs.get('categories', [''])[0].split(',') if c]
    statuses = [s for s in qs.get('statuses', [''])[0].split(',') if s]

    filtered = []
    for job in jobs:
        text = text_blob(job)
        if statuses:
            if job.get('status') not in statuses:
                continue
        elif status_filter and job.get('status') != status_filter:
            continue
        if categories:
            if job.get('category') not in categories:
                continue
        elif category and job.get('category') != category:
            continue
        if q:
            haystack = text if qmode == 'full' else f"{job.get('company', '')} {job.get('role', '')}".lower()
            if q not in haystack:
                continue
        if exclude_terms and any(term in text for term in exclude_terms):
            continue
        if tab == 'automation' and not any(kw in text for kw in AUTO_KEYWORDS):
            continue
        if tab == 'earlycareers':
            if not any(kw in text for kw in EARLY_GOOD):
                continue
            if any(kw in text for kw in EARLY_BAD):
                continue
        if tab == 'cfa' and not any(kw in text for kw in CFA_KEYWORDS):
            continue
        if tab == 'fallfinance' and not is_fall_finance_target(job):
            continue
        if tab == 'applied' and job.get('status') != 'applied':
            continue
        if tab == 'interviews' and job.get('status') != 'interview':
            continue

        job = dict(job)
        job['_firmLabel'] = infer_firm_label(job)

        if tab == 'bestmatch':
            match = score_match(job)
            if match['score'] < 5:
                continue
            job['_matchScore'] = match['score']
            job['_bestResume'] = match['bestResume']
            job['_chance'] = match['chance']
            job['_matchReasons'] = match['reasons']
        elif tab == 'fallfinance':
            match = score_match(job)
            job['_matchScore'] = match['score']
            job['_bestResume'] = match['bestResume']
            job['_chance'] = match['chance']
            job['_matchReasons'] = match['reasons']
        filtered.append(job)

    SORT_KEYS = {
        'company': lambda j: (j.get('company') or '').lower(),
        'role': lambda j: (j.get('role') or '').lower(),
        'category': lambda j: (j.get('category') or '').lower(),
        'status': lambda j: (j.get('status') or '').lower(),
        'location': lambda j: (j.get('location') or '').lower(),
        'priority': lambda j: P_MAP.get(j.get('priority', 'medium'), 1),
        'date_added': lambda j: j.get('date_added') or '',
        'date_applied': lambda j: j.get('date_applied') or '',
        'deadline': lambda j: j.get('deadline') or '',
    }
    if tab == 'search' and sort in SORT_KEYS:
        reverse = (sort_dir == 'desc') if sort_dir else (sort in ('date_added', 'date_applied', 'deadline'))
        filtered.sort(key=SORT_KEYS[sort], reverse=reverse)
    elif sort == 'priority':
        filtered.sort(key=lambda j: (P_MAP.get(j.get('priority', 'medium'), 1), -(j.get('_matchScore') or 0)))
    elif sort == 'company':
        filtered.sort(key=lambda j: j.get('company', '').lower())
    elif tab == 'bestmatch':
        filtered.sort(key=lambda j: j.get('_matchScore', 0), reverse=True)
    elif tab == 'fallfinance':
        firm_rank = {'Top Tier': 0, 'Large Firm': 1, 'Institutional': 2, 'Boutique': 3, 'Finance Firm': 4, 'Other': 5}
        filtered.sort(key=lambda j: (firm_rank.get(j.get('_firmLabel'), 9), -(j.get('_matchScore') or 0), j.get('company', '').lower()))
    elif tab == 'micromature':
        firm_rank = {'Boutique': 0, 'Finance Firm': 1, 'Other': 2, 'Large Firm': 3, 'Institutional': 4, 'Top Tier': 5}
        filtered.sort(key=lambda j: (firm_rank.get(j.get('_firmLabel'), 9), P_MAP.get(j.get('priority', 'medium'), 1), j.get('company', '').lower()))
    else:
        reverse = (sort_dir != 'asc')
        filtered.sort(key=lambda j: j.get('date_added') or '', reverse=reverse)
    return filtered


def summarize_job(job):
    keep = [
        'id', 'company', 'role', 'tier', 'category', 'url', 'careers_url', 'salary_range', 'location',
        'status', 'notes', 'date_added', 'date_applied', 'priority', 'deadline',
        '_matchScore', '_bestResume', '_chance', '_matchReasons', '_firmLabel'
    ]
    out = {k: job.get(k) for k in keep if k in job}
    if out.get('notes') and len(out['notes']) > 240:
        out['notes_preview'] = out['notes'][:240] + '…'
    return out


class handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def send_json(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        for k, v in cors_headers().items():
            self.send_header(k, v)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def check_auth(self):
        token = self.headers.get('X-Auth-Token', '')
        return bool(VALID_TOKEN) and token == VALID_TOKEN

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in cors_headers().items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path.rstrip('/')

        if path == '/api/auth':
            pw = qs.get('password', [''])[0]
            if PASSWORD and pw == PASSWORD:
                return self.send_json(200, {'token': VALID_TOKEN, 'ok': True})
            return self.send_json(401, {'error': 'Invalid password'})

        if path == '/api/jobs':
            job_id = qs.get('id', [''])[0]
            try:
                if job_id:
                    job = get_job(job_id)
                    if not job:
                        return self.send_json(404, {'error': 'Job not found'})
                    return self.send_json(200, job)
                jobs = load_all_jobs().get('jobs', [])
            except Exception as e:
                print(f"DB read error: {e}")
                return self.send_json(500, {'error': 'Database error'})

            filtered = apply_filters(jobs, qs)
            total_filtered = len(filtered)
            try:
                page = max(int(qs.get('page', ['1'])[0]), 1)
            except Exception:
                page = 1
            try:
                page_size = int(qs.get('page_size', ['40'])[0])
            except Exception:
                page_size = 40
            page_size = max(1, min(page_size, 100))
            start = (page - 1) * page_size
            end = start + page_size
            paged = filtered[start:end]
            slim = qs.get('detail', ['summary'])[0] != 'full'
            jobs_out = [summarize_job(j) for j in paged] if slim else paged
            return self.send_json(200, {
                'jobs': jobs_out,
                'meta': build_meta(jobs),
                'page': page,
                'page_size': page_size,
                'total_filtered': total_filtered,
                'has_more': end < total_filtered,
            })

        self.send_json(404, {'error': 'Not found'})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip('/')
        if path != '/api/jobs':
            return self.send_json(404, {'error': 'Not found'})
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length).decode())
        try:
            tier = int(body.get('tier', 4))
        except Exception:
            tier = 4
        new_job = {
            'id': str(uuid.uuid4()),
            'company': body.get('company', ''),
            'role': body.get('role', ''),
            'tier': tier,
            'category': body.get('category', 'Business Operations'),
            'url': body.get('url', ''),
            'careers_url': body.get('careers_url', ''),
            'salary_range': body.get('salary_range', ''),
            'location': body.get('location', 'Toronto'),
            'status': body.get('status', 'not_applied'),
            'notes': body.get('notes', ''),
            'description': body.get('description', ''),
            'source': body.get('source', 'manual'),
            'date_added': datetime.now().strftime('%Y-%m-%d'),
            'date_applied': body.get('date_applied', None),
            'priority': body.get('priority', 'medium'),
            'deadline': body.get('deadline', None),
        }
        try:
            insert_job(new_job)
        except Exception as e:
            print(f"DB insert error: {e}")
            return self.send_json(500, {'error': 'Failed to save'})
        return self.send_json(201, new_job)

    def do_PATCH(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path.rstrip('/')
        if path != '/api/jobs':
            return self.send_json(404, {'error': 'Not found'})
        job_id = qs.get('id', [''])[0]
        if not job_id:
            return self.send_json(400, {'error': 'Missing id'})
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length).decode())
        allowed = ['status', 'notes', 'date_applied', 'priority', 'deadline', 'company',
                   'role', 'tier', 'category', 'url', 'careers_url', 'salary_range',
                   'location', 'description', 'source']
        fields = {f: body[f] for f in allowed if f in body}
        try:
            existing = get_job(job_id)
            if not existing:
                return self.send_json(404, {'error': 'Job not found'})
            if body.get('status') == 'applied' and not existing.get('date_applied') and not fields.get('date_applied'):
                fields['date_applied'] = datetime.now().strftime('%Y-%m-%d')
            update_job(job_id, fields)
            updated = get_job(job_id)
        except Exception as e:
            print(f"DB update error: {e}")
            return self.send_json(500, {'error': 'Failed to save'})
        return self.send_json(200, updated)

    def do_DELETE(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path.rstrip('/')
        if path != '/api/jobs':
            return self.send_json(404, {'error': 'Not found'})
        job_id = qs.get('id', [''])[0]
        if not job_id:
            return self.send_json(400, {'error': 'Missing id'})
        try:
            if not delete_job(job_id):
                return self.send_json(404, {'error': 'Job not found'})
        except Exception as e:
            print(f"DB delete error: {e}")
            return self.send_json(500, {'error': 'Failed to save'})
        return self.send_json(200, {'ok': True})
