import json
import os
import uuid
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime
import urllib.request

# Auth
PASSWORD = "ratul2026"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GIST_ID = os.environ.get("GIST_ID", "27de5ee2ebb56bd5be8a31102df7bb9c")
GIST_FILE = "jobs.json"

VALID_TOKEN = "jt-" + PASSWORD
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


def gist_read():
    url = f"https://api.github.com/gists/{GIST_ID}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "job-tracker"
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            file_info = data["files"][GIST_FILE]
            raw_url = file_info.get("raw_url")
            if raw_url:
                raw_req = urllib.request.Request(raw_url, headers={"User-Agent": "job-tracker"})
                with urllib.request.urlopen(raw_req, timeout=15) as raw_resp:
                    content = raw_resp.read().decode()
            else:
                content = file_info["content"]
            parsed = json.loads(content)
            if isinstance(parsed, list):
                return {"jobs": parsed}
            elif isinstance(parsed, dict) and "jobs" in parsed:
                return parsed
            else:
                return {"jobs": []}
    except Exception as e:
        print(f"Gist read error: {e}")
        return {"jobs": []}


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


def gist_write(data):
    if isinstance(data, dict) and "jobs" in data:
        write_data = data["jobs"]
    elif isinstance(data, list):
        write_data = data
    else:
        write_data = []
    url = f"https://api.github.com/gists/{GIST_ID}"
    payload = json.dumps({
        "files": {
            GIST_FILE: {
                "content": json.dumps(write_data, indent=2)
            }
        }
    }).encode()
    req = urllib.request.Request(url, data=payload, method="PATCH", headers={
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "job-tracker"
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"Gist write error: {e}")
        return False


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
            "keywords": ['investment analyst', 'portfolio analytics', 'institutional investing', 'manager research', 'asset allocation', 'equity research', 'valuation', 'capital markets', 'cfa', 'investment consulting', 'wealth', 'pension'],
            "titleBoost": ['analyst', 'associate', 'investment'],
        },
        "Consulting": {
            "keywords": ['consulting', 'strategy', 'business operations', 'project management', 'stakeholder', 'process improvement', 'cross-functional', 'operations analyst'],
            "titleBoost": ['analyst', 'associate', 'consulting'],
        }
    }
    negatives_hard = ['10+ year', '8+ year', '7+ year', '6+ year', '5-8 years', '5 to 8 years', 'director', 'vice president', 'vp ', 'principal', 'partner', 'cpa required', 'isda', 'csa', 'trioptima', 'numerix', 'markit', 'aladdin']
    negatives_medium = ['4+ year', '4 years', '5+ year', '5 years', 'senior manager', 'senior ', 'lead ', 'manager', 'derivatives middle office', 'quant developer', 'insurance product forms']
    context_bonus = ['entry level', 'new grad', 'new graduate', 'early career', 'analyst', 'associate', 'coordinator', 'specialist', 'toronto', 'waterloo', 'remote', 'hybrid', 'canada', 'startup', 'saas', 'fintech']
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
        for kw in negatives_hard:
            if kw in text:
                score -= 8
        for kw in negatives_medium:
            if kw in text:
                score -= 4
        if ((('asset management' in text) or ('private equity' in text) or ('equity research' in text) or ('portfolio' in text))
                and resume != 'PE' and not (('new grad' in text) or ('entry level' in text) or ('intern' in text))):
            score -= 3
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
        return token == VALID_TOKEN

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
            if pw == PASSWORD:
                return self.send_json(200, {'token': VALID_TOKEN, 'ok': True})
            return self.send_json(401, {'error': 'Invalid password'})

        if path == '/api/jobs':
            data = gist_read()
            jobs = data.get('jobs', [])
            job_id = qs.get('id', [''])[0]
            if job_id:
                job = next((j for j in jobs if j.get('id') == job_id), None)
                if not job:
                    return self.send_json(404, {'error': 'Job not found'})
                return self.send_json(200, job)

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
        if not self.check_auth():
            return self.send_json(401, {'error': 'Unauthorized'})
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length).decode())
        data = gist_read()
        jobs = data.get('jobs', [])
        new_job = {
            'id': str(uuid.uuid4()),
            'company': body.get('company', ''),
            'role': body.get('role', ''),
            'tier': int(body.get('tier', 4)),
            'category': body.get('category', 'Business Operations'),
            'url': body.get('url', ''),
            'salary_range': body.get('salary_range', ''),
            'location': body.get('location', 'Toronto'),
            'status': body.get('status', 'not_applied'),
            'notes': body.get('notes', ''),
            'date_added': datetime.now().strftime('%Y-%m-%d'),
            'date_applied': body.get('date_applied', None),
            'priority': body.get('priority', 'medium'),
            'deadline': body.get('deadline', None)
        }
        jobs.append(new_job)
        data['jobs'] = jobs
        if gist_write(data):
            return self.send_json(201, new_job)
        return self.send_json(500, {'error': 'Failed to save'})

    def do_PATCH(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path.rstrip('/')
        if path != '/api/jobs':
            return self.send_json(404, {'error': 'Not found'})
        if not self.check_auth():
            return self.send_json(401, {'error': 'Unauthorized'})
        job_id = qs.get('id', [''])[0]
        if not job_id:
            return self.send_json(400, {'error': 'Missing id'})
        length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(length).decode())
        data = gist_read()
        jobs = data.get('jobs', [])
        updated = None
        for job in jobs:
            if job['id'] == job_id:
                allowed = ['status', 'notes', 'date_applied', 'priority', 'deadline', 'company', 'role', 'tier', 'category', 'url', 'salary_range', 'location']
                for field in allowed:
                    if field in body:
                        job[field] = body[field]
                if body.get('status') == 'applied' and not job.get('date_applied'):
                    job['date_applied'] = datetime.now().strftime('%Y-%m-%d')
                updated = job
                break
        if not updated:
            return self.send_json(404, {'error': 'Job not found'})
        data['jobs'] = jobs
        if gist_write(data):
            return self.send_json(200, updated)
        return self.send_json(500, {'error': 'Failed to save'})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path.rstrip('/')
        if path != '/api/jobs':
            return self.send_json(404, {'error': 'Not found'})
        if not self.check_auth():
            return self.send_json(401, {'error': 'Unauthorized'})
        job_id = qs.get('id', [''])[0]
        if not job_id:
            return self.send_json(400, {'error': 'Missing id'})
        data = gist_read()
        jobs = data.get('jobs', [])
        original_len = len(jobs)
        jobs = [j for j in jobs if j['id'] != job_id]
        if len(jobs) == original_len:
            return self.send_json(404, {'error': 'Job not found'})
        data['jobs'] = jobs
        if gist_write(data):
            return self.send_json(200, {'ok': True})
        return self.send_json(500, {'error': 'Failed to save'})
