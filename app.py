from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime, date, timedelta
from functools import wraps
import os, hashlib, json, calendar, random, string

# ── Database: PostgreSQL on Railway, SQLite locally ────────────────────────────
DATABASE_URL = os.environ.get('DATABASE_URL', '')

if DATABASE_URL:
    import psycopg2, psycopg2.extras
    PG = True
else:
    import sqlite3
    PG = False
    DB_PATH = os.path.join(os.path.dirname(__file__), 'instance', 'hr_master.db')

app = Flask(__name__)
app.jinja_env.globals.update(enumerate=enumerate)
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.secret_key = os.environ.get('SECRET_KEY', 'hr_mitra_karya_2026_secret')

# Custom Jinja2 filter: format date safely for both SQLite (string) and PostgreSQL (datetime)
@app.template_filter('datestr')
def datestr_filter(value):
    if value is None: return '—'
    if hasattr(value, 'strftime'):
        return value.strftime('%d %b %Y')
    try:
        return str(value)[:10]
    except:
        return str(value)
DEPARTMENTS_POSITIONS = {
    "Finishing": ["Padder Dryer", "Centrifugal & Scutcher", "Calendar & Compactor", "Setting"],
    "Dyeing": ["Dyeing"],
    "Quality Control": ["Quality Control (QC)"],
    "Boiler": ["Boiler"],
    "Umum": ["Proyek", "Bongkar Muat", "Umum"],
    "Staff": ["Staff Chemical", "Staff Batubara & Sparepart", "Staff Finishing 1",
              "Staff Finishing 2", "Staff Dyeing", "Staff Greige", "Staff Ekspedisi"],
    "LAB": ["LAB 1", "LAB 2", "LAB 3"],
    "Security": ["Security"],
    "Gudang Obat": ["Gudang Obat"],
    "Personalia": ["Staff Personalia"],
    "Resepsionis": ["Resepsionis"],
}

PROVINCES = [
    "Aceh","Bali","Bangka Belitung","Banten","Bengkulu","DI Yogyakarta","DKI Jakarta",
    "Gorontalo","Jambi","Jawa Barat","Jawa Tengah","Jawa Timur","Kalimantan Barat",
    "Kalimantan Selatan","Kalimantan Tengah","Kalimantan Timur","Kalimantan Utara",
    "Kepulauan Riau","Lampung","Maluku","Maluku Utara","Nusa Tenggara Barat",
    "Nusa Tenggara Timur","Papua","Papua Barat","Papua Barat Daya","Papua Pegunungan",
    "Papua Selatan","Papua Tengah","Riau","Sulawesi Barat","Sulawesi Selatan",
    "Sulawesi Tengah","Sulawesi Tenggara","Sulawesi Utara","Sumatera Barat",
    "Sumatera Selatan","Sumatera Utara",
]

RELIGIONS = ["Islam","Kristen Protestan","Kristen Katolik","Hindu","Buddha","Konghucu"]

DISCIPLINE_TYPES = {
    "Surat Teguran":             {"code":"TGR","desc":"Teguran resmi tertulis atas pelanggaran atau perilaku tidak sesuai"},
    "Surat Peringatan 1 (SP1)":  {"code":"SP1","desc":"Peringatan pertama secara tertulis"},
    "Surat Peringatan 2 (SP2)":  {"code":"SP2","desc":"Peringatan kedua setelah SP1 tidak diindahkan"},
    "Surat Peringatan 3 (SP3)":  {"code":"SP3","desc":"Peringatan terakhir — hubungan kerja berakhir"},
    "Surat Kelalaian":           {"code":"KLL","desc":"Staff lalai menjalankan tanggung jawab hingga menyebabkan masalah"},
    "Surat Pelanggaran Kontrak": {"code":"PLG","desc":"Staff melanggar isi kontrak — resign sebelum habis atau tindakan yang mengakhiri kontrak"},
}

DOC_TYPES = {
    "DP - Dokumen Pelamar":           {"code":"DP",  "need_reason":False,"need_drive":True, "desc":"Kumpulan dokumen lamaran karyawan"},
    "KTR - Kontrak":                  {"code":"KTR", "need_reason":False,"need_drive":False,"desc":"Dokumen kontrak kerja — tidak perlu di-scan"},
    "RZN - Surat Pengunduran Diri":   {"code":"RZN", "need_reason":True, "need_drive":True, "desc":"Surat resign — wajib isi alasan"},
    "IZN - Surat Izin":               {"code":"IZN", "need_reason":True, "need_drive":True, "desc":"Surat izin tidak masuk — wajib isi alasan"},
    "DR - Surat Dokter":              {"code":"DR",  "need_reason":False,"need_drive":True, "desc":"Surat keterangan sakit dari dokter"},
    "PYT - Surat Pernyataan":         {"code":"PYT", "need_reason":False,"need_drive":True, "desc":"Surat pernyataan yang ditandatangani staff"},
    "OFF - Surat Penukaran/Masuk Off":{"code":"OFF", "need_reason":True, "need_drive":True, "desc":"Permintaan tukar hari off atau masuk saat off — wajib isi alasan"},
    "LMB - Surat Lembur":             {"code":"LMB", "need_reason":True, "need_drive":True, "desc":"Permintaan lembur melebihi jam normal — wajib isi alasan"},
    "HBK - Surat Habis Kontrak":      {"code":"HBK", "need_reason":False,"need_drive":True, "desc":"Surat pemberitahuan kontrak staff telah berakhir"},
    "BBU - Surat Bebas Urusan":       {"code":"BBU", "need_reason":False,"need_drive":True, "desc":"Surat clearance setelah kontrak berakhir"},
    "PIN - Surat Pengajuan Insentif": {"code":"PIN", "need_reason":False,"need_drive":True, "desc":"Pengajuan pencairan insentif yang sudah jatuh tempo"},
}

DP_CHECKLIST = [
    {"key":"cv",        "label":"Daftar Riwayat Hidup (CV)",                 "optional":False},
    {"key":"ktp",       "label":"Fotokopi KTP",                               "optional":False},
    {"key":"ijazah",    "label":"Fotokopi Ijazah",                            "optional":False},
    {"key":"sks",       "label":"SKS — Surat Keterangan Sehat",               "optional":False},
    {"key":"skck",      "label":"SKCK — Surat Keterangan Catatan Kepolisian", "optional":False},
    {"key":"kk",        "label":"KK — Kartu Keluarga",                        "optional":False},
    {"key":"akte",      "label":"Akte Lahir",                                  "optional":False},
    {"key":"lamaran",   "label":"Surat Lamaran (Cover Letter)",                "optional":False},
    {"key":"pengalaman","label":"Surat Pengalaman Kerja",                      "optional":True},
    {"key":"foto",      "label":"Pas Foto 3×4 (2 lembar)",                    "optional":False},
]

EXIT_REASONS = {
    "Resign (kontrak sudah habis)": {"docs":["RZN","HBK","BBU"]},
    "Pelanggaran Kontrak":          {"docs":["PLG","RZN","BBU"]},
    "SP3 — Terminasi":              {"docs":["RZN","PLG","BBU"]},
    "Tidak Lulus Evaluasi":         {"docs":["RZN","HBK","BBU"]},
}

SPONSOR_FEE = 100000

# ── Unified DB wrapper ─────────────────────────────────────────────────────────
class DB:
    """Works transparently with both SQLite and PostgreSQL.
    Usage: with DB() as db: db.execute(...) / db.fetchone(...) / db.fetchall(...)
    """
    def __init__(self):
        if PG:
            url = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
            self.conn = psycopg2.connect(url)
        else:
            self.conn = sqlite3.connect(DB_PATH)
            self.conn.row_factory = sqlite3.Row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, *_):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        self.conn.close()

    def _sql(self, sql):
        """Translate SQLite SQL to PostgreSQL if needed"""
        if PG:
            sql = sql.replace('?', '%s')
            sql = sql.replace("datetime('now','localtime')", 'NOW()')
            sql = sql.replace("datetime('now')", 'NOW()')
        return sql

    def _row(self, row):
        """Normalise a DB row to a plain dict (safe after connection closes)"""
        if row is None: return None
        if PG: return dict(row)
        return dict(row)  # convert sqlite3.Row to plain dict immediately

    def execute(self, sql, params=()):
        if PG:
            cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            cur.execute(self._sql(sql), params)
            return cur
        else:
            return self.conn.execute(self._sql(sql), params)

    def fetchone(self, sql, params=()):
        cur = self.execute(sql, params)
        return self._row(cur.fetchone())

    def fetchall(self, sql, params=()):
        cur = self.execute(sql, params)
        rows = cur.fetchall()
        return [self._row(r) for r in rows]

    def fetchval(self, sql, params=()):
        """Fetch single value (e.g. COUNT)"""
        row = self.fetchone(sql, params)
        if row is None: return 0
        # Both PG and SQLite now return dicts, so get first value
        if isinstance(row, dict):
            return list(row.values())[0]
        return row[0]

    def insert(self, sql, params=()):
        """Execute INSERT and return the new row id"""
        if PG:
            sql_r = self._sql(sql) + ' RETURNING id'
            cur = self.conn.cursor()
            cur.execute(sql_r, params)
            result = cur.fetchone()
            return result[0] if result else None
        else:
            cur = self.conn.execute(self._sql(sql), params)
            return cur.lastrowid

    def commit(self):
        self.conn.commit()

    def executescript(self, sql):
        """Only used by SQLite init"""
        if not PG:
            self.conn.executescript(sql)


# ── keep old get_db() name so existing route code works unchanged ──────────────
def get_db():
    return DB()


def init_db():
    if PG:
        url = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
        conn = psycopg2.connect(url)
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY, username VARCHAR(100) UNIQUE NOT NULL,
            password VARCHAR(200) NOT NULL, full_name VARCHAR(200) NOT NULL,
            role VARCHAR(50) NOT NULL DEFAULT 'hr_staff',
            created_at TIMESTAMP DEFAULT NOW())""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS staff (
            id SERIAL PRIMARY KEY, emp_id VARCHAR(20) UNIQUE NOT NULL,
            full_name VARCHAR(200) NOT NULL, ktp_number VARCHAR(20) NOT NULL,
            birth_date VARCHAR(20) NOT NULL, birth_place VARCHAR(100) NOT NULL DEFAULT '', gender VARCHAR(20) NOT NULL,
            religion VARCHAR(50) NOT NULL DEFAULT 'Islam',
            address TEXT NOT NULL, rt_rw VARCHAR(20) NOT NULL DEFAULT '',
            kelurahan VARCHAR(100) NOT NULL DEFAULT '',
            kecamatan VARCHAR(100) NOT NULL DEFAULT '',
            kota VARCHAR(100) NOT NULL, provinsi VARCHAR(100) NOT NULL,
            phone VARCHAR(30) NOT NULL, position VARCHAR(100) NOT NULL,
            department VARCHAR(100) NOT NULL, education VARCHAR(50) NOT NULL,
            emergency_contact VARCHAR(200) NOT NULL,
            emergency_relationship VARCHAR(100) NOT NULL,
            emergency_phone VARCHAR(30) NOT NULL,
            status VARCHAR(20) DEFAULT 'AKTIF',
            is_blacklisted INTEGER DEFAULT 0, blacklist_reason TEXT,
            pkwt_reregister INTEGER DEFAULT 0,
            created_by VARCHAR(100), created_at TIMESTAMP DEFAULT NOW(),
            updated_by VARCHAR(100), updated_at TIMESTAMP)""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS employment_periods (
            id SERIAL PRIMARY KEY, staff_id INTEGER NOT NULL,
            period_number INTEGER NOT NULL, staff_type VARCHAR(30) NOT NULL,
            start_date VARCHAR(20) NOT NULL, contract_end_date VARCHAR(20),
            end_date VARCHAR(20), end_reason VARCHAR(100),
            evaluation_result VARCHAR(100), evaluation_notes TEXT,
            salary_increase VARCHAR(200), bpjs_enrolled INTEGER DEFAULT 0,
            sponsor_name VARCHAR(200), status VARCHAR(20) DEFAULT 'AKTIF',
            created_by VARCHAR(100), created_at TIMESTAMP DEFAULT NOW())""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS discipline_records (
            id SERIAL PRIMARY KEY, staff_id INTEGER NOT NULL,
            period_id INTEGER NOT NULL, sp_type VARCHAR(100) NOT NULL,
            doc_code VARCHAR(10) NOT NULL, incident_date VARCHAR(20) NOT NULL,
            description TEXT NOT NULL, doc_ref VARCHAR(50) UNIQUE NOT NULL,
            drive_path TEXT, physical_location VARCHAR(200),
            created_by VARCHAR(100), created_at TIMESTAMP DEFAULT NOW())""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id SERIAL PRIMARY KEY, staff_id INTEGER NOT NULL,
            doc_type VARCHAR(100) NOT NULL, doc_code VARCHAR(10) NOT NULL,
            doc_ref VARCHAR(50) UNIQUE NOT NULL,
            description TEXT, reason TEXT, dp_checklist TEXT, dp_others TEXT,
            drive_path TEXT, physical_location VARCHAR(200),
            need_drive INTEGER DEFAULT 1,
            created_by VARCHAR(100), created_at TIMESTAMP DEFAULT NOW())""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_log (
            id SERIAL PRIMARY KEY, username VARCHAR(100) NOT NULL,
            role VARCHAR(50), action VARCHAR(100) NOT NULL,
            table_name VARCHAR(50), record_id INTEGER, details TEXT,
            created_at TIMESTAMP DEFAULT NOW())""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS id_counter (
            prefix VARCHAR(50) PRIMARY KEY, last_number INTEGER DEFAULT 0)""")
        try: cur.execute("ALTER TABLE staff ADD COLUMN birth_place VARCHAR(100) NOT NULL DEFAULT ''")
        except: pass
        conn.commit()
        # Default users
        def pw(p): return hashlib.sha256(p.encode()).hexdigest()
        for u,p,n,r in [('owner',pw('owner123'),'Owner','owner'),
                         ('admin',pw('admin123'),'HR Head','hr_head'),
                         ('hrstaff',pw('staff123'),'HR Staff','hr_staff')]:
            try:
                cur.execute("INSERT INTO users (username,password,full_name,role) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",(u,p,n,r))
            except: pass
        conn.commit()
        conn.close()
    else:
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        with DB() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL, password TEXT NOT NULL,
                full_name TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'hr_staff',
                created_at TEXT DEFAULT (datetime('now','localtime')));
            CREATE TABLE IF NOT EXISTS staff (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                emp_id TEXT UNIQUE NOT NULL, full_name TEXT NOT NULL,
                ktp_number TEXT NOT NULL, birth_date TEXT NOT NULL,
                birth_place TEXT NOT NULL DEFAULT '', gender TEXT NOT NULL, religion TEXT NOT NULL DEFAULT 'Islam',
                address TEXT NOT NULL, rt_rw TEXT NOT NULL DEFAULT '',
                kelurahan TEXT NOT NULL DEFAULT '',
                kecamatan TEXT NOT NULL DEFAULT '',
                kota TEXT NOT NULL, provinsi TEXT NOT NULL, phone TEXT NOT NULL,
                position TEXT NOT NULL, department TEXT NOT NULL,
                education TEXT NOT NULL,
                emergency_contact TEXT NOT NULL,
                emergency_relationship TEXT NOT NULL,
                emergency_phone TEXT NOT NULL,
                status TEXT DEFAULT 'AKTIF',
                is_blacklisted INTEGER DEFAULT 0, blacklist_reason TEXT,
                pkwt_reregister INTEGER DEFAULT 0, created_by TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')),
                updated_by TEXT, updated_at TEXT);
            CREATE TABLE IF NOT EXISTS employment_periods (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_id INTEGER NOT NULL, period_number INTEGER NOT NULL,
                staff_type TEXT NOT NULL, start_date TEXT NOT NULL,
                contract_end_date TEXT, end_date TEXT, end_reason TEXT,
                evaluation_result TEXT, evaluation_notes TEXT,
                salary_increase TEXT, bpjs_enrolled INTEGER DEFAULT 0,
                sponsor_name TEXT, status TEXT DEFAULT 'AKTIF',
                created_by TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')));
            CREATE TABLE IF NOT EXISTS discipline_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_id INTEGER NOT NULL, period_id INTEGER NOT NULL,
                sp_type TEXT NOT NULL, doc_code TEXT NOT NULL,
                incident_date TEXT NOT NULL, description TEXT NOT NULL,
                doc_ref TEXT UNIQUE NOT NULL, drive_path TEXT,
                physical_location TEXT, created_by TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')));
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_id INTEGER NOT NULL, doc_type TEXT NOT NULL,
                doc_code TEXT NOT NULL, doc_ref TEXT UNIQUE NOT NULL,
                description TEXT, reason TEXT, dp_checklist TEXT,
                dp_others TEXT, drive_path TEXT, physical_location TEXT,
                need_drive INTEGER DEFAULT 1, created_by TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')));
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL, role TEXT, action TEXT NOT NULL,
                table_name TEXT, record_id INTEGER, details TEXT,
                created_at TEXT DEFAULT (datetime('now','localtime')));
            CREATE TABLE IF NOT EXISTS id_counter (
                prefix TEXT PRIMARY KEY, last_number INTEGER DEFAULT 0);
            ''')
            for table, col, defn in [
                ("staff","birth_place","TEXT NOT NULL DEFAULT ''"),
                ("staff","religion","TEXT NOT NULL DEFAULT 'Islam'"),
                ("staff","rt_rw","TEXT NOT NULL DEFAULT ''"),
                ("staff","kelurahan","TEXT NOT NULL DEFAULT ''"),
                ("staff","kecamatan","TEXT NOT NULL DEFAULT ''"),
                ("staff","pkwt_reregister","INTEGER DEFAULT 0"),
                ("employment_periods","evaluation_notes","TEXT"),
                ("employment_periods","salary_increase","TEXT"),
                ("employment_periods","bpjs_enrolled","INTEGER DEFAULT 0"),
                ("documents","dp_checklist","TEXT"),
                ("documents","dp_others","TEXT"),
                ("audit_log","role","TEXT"),
            ]:
                try: db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {defn}")
                except: pass
            def pw(p): return hashlib.sha256(p.encode()).hexdigest()
            for u,p,n,r in [('owner',pw('owner123'),'Owner','owner'),
                             ('admin',pw('admin123'),'HR Head','hr_head'),
                             ('hrstaff',pw('staff123'),'HR Staff','hr_staff')]:
                try: db.execute("INSERT INTO users (username,password,full_name,role) VALUES (?,?,?,?)",(u,p,n,r))
                except: pass

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if session.get('role') not in roles:
                flash('Akses ditolak.','error')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return decorated
    return decorator

def is_head_or_owner(): return session.get('role') in ('hr_head','owner')
def is_owner():         return session.get('role') == 'owner'

def gen_emp_id():
    with get_db() as db:
        row = db.fetchone("SELECT last_number FROM id_counter WHERE prefix='NIP'")
        n = (row['last_number']+1) if row else 26001
        if n < 26001: n = 26001
        db.execute("INSERT OR REPLACE INTO id_counter (prefix,last_number) VALUES ('NIP',?)",(n,))
        db.commit()
    return str(n)

def gen_doc_ref(emp_id, code):
    key = f"{emp_id}-{code}"
    with get_db() as db:
        row = db.fetchone("SELECT last_number FROM id_counter WHERE prefix=?", (key,))
        n = (row['last_number']+1) if row else 1
        db.execute("INSERT OR REPLACE INTO id_counter (prefix,last_number) VALUES (?,?)",(key,n))
        db.commit()
    return f"{emp_id}-{code}-{n:03d}"

def log_audit(action, table=None, record_id=None, details=None):
    with get_db() as db:
        db.execute("INSERT INTO audit_log (username,role,action,table_name,record_id,details) VALUES (?,?,?,?,?,?)",
                  (session.get('user','?'),session.get('role','?'),action,table,record_id,details))
        db.commit()

def get_pkwt_total_days(staff_id):
    with get_db() as db:
        periods = db.fetchall(
            "SELECT start_date,end_date,contract_end_date,status FROM employment_periods WHERE staff_id=? AND staff_type='PKWT'",
            (staff_id,))
    total, today = 0, date.today()
    for p in periods:
        start = datetime.strptime(p['start_date'],'%Y-%m-%d').date()
        if p['status']=='AKTIF': end = today
        elif p['end_date']:      end = datetime.strptime(p['end_date'],'%Y-%m-%d').date()
        elif p['contract_end_date']: end = datetime.strptime(p['contract_end_date'],'%Y-%m-%d').date()
        else: end = today
        total += (end-start).days
    return total

def sponsor_fee_this_month(sponsor_name):
    today = date.today()
    month_start = date(today.year,today.month,1)
    days_in_month = calendar.monthrange(today.year,today.month)[1]
    with get_db() as db:
        rows = db.fetchall("""SELECT ep.start_date,ep.end_date,ep.status
                              FROM employment_periods ep JOIN staff s ON ep.staff_id=s.id
                              WHERE ep.sponsor_name=? AND ep.staff_type='HL-Outsource'
                              AND s.status='AKTIF'""", (sponsor_name,))
    total = 0
    for r in rows:
        start = datetime.strptime(r['start_date'],'%Y-%m-%d').date()
        work_start = max(start,month_start)
        work_end = today
        days = max(0,(work_end-work_start).days+1)
        total += SPONSOR_FEE/days_in_month*days
    return round(total)

def get_alerts_and_todos():
    alerts, todos = [], []
    today = date.today()
    with get_db() as db:
        if is_head_or_owner():
            # Contract expiry
            periods = db.fetchall("""SELECT ep.*,s.full_name,s.emp_id,s.id as staff_id
                                    FROM employment_periods ep JOIN staff s ON ep.staff_id=s.id
                                    WHERE ep.status='AKTIF' AND ep.contract_end_date IS NOT NULL""")
            for p in periods:
                end = datetime.strptime(p['contract_end_date'],'%Y-%m-%d').date()
                days = (end-today).days
                if days < 0:
                    alerts.append({'level':'critical','msg':f"Kontrak {p['full_name']} ({p['emp_id']}) SUDAH HABIS sejak {end.strftime('%d %b %Y')}","staff_id":p['staff_id']})
                elif days <= 7:
                    alerts.append({'level':'danger','msg':f"Kontrak {p['full_name']} ({p['emp_id']}) habis dalam {days} hari ({end.strftime('%d %b %Y')})","staff_id":p['staff_id']})
                elif days <= 30:
                    alerts.append({'level':'warning','msg':f"Kontrak {p['full_name']} ({p['emp_id']}) habis dalam {days} hari ({end.strftime('%d %b %Y')})","staff_id":p['staff_id']})

            # PKWT 2-year / 3-year
            pkwt_active = db.fetchall("""SELECT DISTINCT s.id,s.full_name,s.emp_id
                                         FROM employment_periods ep JOIN staff s ON ep.staff_id=s.id
                                         WHERE ep.staff_type='PKWT' AND ep.status='AKTIF'""")
            for s in pkwt_active:
                td = get_pkwt_total_days(s['id'])
                yrs = td/365
                if yrs >= 3:
                    alerts.append({'level':'critical','msg':f"⚠ {s['full_name']} ({s['emp_id']}) MELEBIHI batas maksimal 3 tahun PKWT ({td} hari)","staff_id":s['id']})
                elif yrs >= 2:
                    alerts.append({'level':'danger','msg':f"📋 {s['full_name']} ({s['emp_id']}) sudah 2 tahun PKWT — wajib resign, tunggu 3 hari, lalu daftar ulang NIP baru","staff_id":s['id']})

        # To-do: drive pending
        for d in db.fetchall("""SELECT s.full_name,s.emp_id,s.id as staff_id,d.doc_ref,d.doc_type
                                FROM documents d JOIN staff s ON d.staff_id=s.id
                                WHERE (d.drive_path IS NULL OR d.drive_path='') AND d.need_drive=1
                                ORDER BY d.created_at DESC LIMIT 10"""):
            todos.append({'type':'drive','msg':f"{d['full_name']} ({d['emp_id']}) — {d['doc_type']} [{d['doc_ref']}] belum di-upload ke Drive","staff_id":d['staff_id']})

        for d in db.fetchall("""SELECT s.full_name,s.emp_id,s.id as staff_id,dr.doc_ref,dr.sp_type
                                FROM discipline_records dr JOIN staff s ON dr.staff_id=s.id
                                WHERE dr.drive_path IS NULL OR dr.drive_path=''
                                ORDER BY dr.created_at DESC LIMIT 10"""):
            todos.append({'type':'drive','msg':f"{d['full_name']} ({d['emp_id']}) — {d['sp_type']} [{d['doc_ref']}] belum di-upload ke Drive","staff_id":d['staff_id']})

        # To-do: physical pending (only if drive filled)
        for d in db.fetchall("""SELECT s.full_name,s.emp_id,s.id as staff_id,d.doc_ref,d.doc_type
                                FROM documents d JOIN staff s ON d.staff_id=s.id
                                WHERE (d.physical_location IS NULL OR d.physical_location='')
                                AND d.drive_path IS NOT NULL AND d.drive_path!=''
                                ORDER BY d.created_at DESC LIMIT 10"""):
            todos.append({'type':'physical','msg':f"{d['full_name']} ({d['emp_id']}) — {d['doc_type']} [{d['doc_ref']}] belum diisi lokasi fisik","staff_id":d['staff_id']})

        # To-do: DP missing
        for d in db.fetchall("""SELECT s.full_name,s.emp_id,s.id as staff_id FROM staff s
                                WHERE s.status='AKTIF'
                                AND s.id NOT IN (SELECT staff_id FROM documents WHERE doc_code='DP')
                                ORDER BY s.created_at DESC LIMIT 10"""):
            todos.append({'type':'dp','msg':f"DP {d['full_name']} ({d['emp_id']}) belum diinput","staff_id":d['staff_id']})

        # To-do: evaluation due (head/owner only)
        if is_head_or_owner():
            for e in db.fetchall("""SELECT s.full_name,s.emp_id,s.id as staff_id,ep.start_date
                                    FROM employment_periods ep JOIN staff s ON ep.staff_id=s.id
                                    WHERE ep.status='AKTIF' AND ep.staff_type IN ('HL-Lamaran','HL-Outsource')
                                    AND ep.evaluation_result IS NULL"""):
                start = datetime.strptime(e['start_date'],'%Y-%m-%d').date()
                days_to = ((start+timedelta(days=90))-today).days
                if days_to <= 14:
                    lbl = f"dalam {days_to} hari" if days_to>=0 else f"{abs(days_to)} hari lalu — TERLAMBAT"
                    todos.append({'type':'eval','msg':f"Evaluasi {e['full_name']} ({e['emp_id']}) jatuh tempo {lbl}","staff_id":e['staff_id']})

    return alerts, todos

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        pw = hashlib.sha256(request.form['password'].encode()).hexdigest()
        with get_db() as db:
            user = db.fetchone("SELECT * FROM users WHERE username=? AND password=?", (request.form['username'],pw))
        if user:
            session['user']      = user['username']
            session['role']      = user['role']
            session['full_name'] = user['full_name']
            log_audit('LOGIN')
            return redirect(url_for('dashboard'))
        flash('Username atau password salah.','error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    log_audit('LOGOUT')
    session.clear()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def dashboard():
    with get_db() as db:
        total_aktif = db.fetchval("SELECT COUNT(*) FROM staff WHERE status='AKTIF'")
        total_hl    = db.fetchval("SELECT COUNT(*) FROM employment_periods WHERE status='AKTIF' AND staff_type IN ('HL-Lamaran','HL-Outsource')")
        total_pkwt  = db.fetchval("SELECT COUNT(*) FROM employment_periods WHERE status='AKTIF' AND staff_type='PKWT'")
        total_bl    = db.fetchval("SELECT COUNT(*) FROM staff WHERE is_blacklisted=1")
        recent      = db.fetchall("""SELECT s.full_name,s.emp_id,s.department,s.id,ep.staff_type
                                    FROM staff s JOIN employment_periods ep ON s.id=ep.staff_id
                                    WHERE ep.status='AKTIF' ORDER BY ep.created_at DESC LIMIT 5""")
    alerts, todos = get_alerts_and_todos()
    return render_template('dashboard.html', total_aktif=total_aktif, total_hl=total_hl,
                          total_pkwt=total_pkwt, total_bl=total_bl, recent=recent,
                          alerts=alerts, todos=todos, is_head_or_owner=is_head_or_owner())

@app.route('/staff')
@login_required
def staff_list():
    search = request.args.get('q','')
    dept   = request.args.get('dept','')
    status = request.args.get('status','AKTIF')
    with get_db() as db:
        q = """SELECT s.*,ep.staff_type,ep.contract_end_date,ep.sponsor_name
               FROM staff s LEFT JOIN employment_periods ep ON s.id=ep.staff_id AND ep.status='AKTIF'
               WHERE 1=1"""
        params = []
        if search:
            q += " AND (s.full_name LIKE ? OR s.emp_id LIKE ? OR s.ktp_number LIKE ?)"
            params += [f'%{search}%']*3
        if dept:
            q += " AND s.department=?"; params.append(dept)
        if status=='AKTIF':         q += " AND s.status='AKTIF'"
        elif status=='TIDAK_AKTIF': q += " AND s.status='TIDAK_AKTIF' AND s.is_blacklisted=0"
        elif status=='BLACKLIST':   q += " AND s.is_blacklisted=1"
        q += " ORDER BY s.full_name"
        staff = db.fetchall(q,params)
    return render_template('staff_list.html', staff=staff, search=search, dept=dept,
                          status=status, depts=list(DEPARTMENTS_POSITIONS.keys()))

@app.route('/staff/add', methods=['GET','POST'])
@login_required
def add_staff():
    if request.method == 'POST':
        ktp = request.form['ktp_number'].strip()
        with get_db() as db:
            existing = db.fetchone("SELECT * FROM staff WHERE ktp_number=?", (ktp,))
            if existing:
                if existing['is_blacklisted']:
                    flash(f'⛔ STAFF INI DIBLACKLIST — {existing["blacklist_reason"]}. Hubungi HR Head.','error')
                    return redirect(url_for('add_staff'))
                last = db.fetchone("SELECT * FROM employment_periods WHERE staff_id=? ORDER BY id DESC LIMIT 1", (existing['id'],))
                if last and last['end_date']:
                    end = datetime.strptime(last['end_date'],'%Y-%m-%d').date()
                    days_since = (date.today()-end).days
                    if days_since < 3:
                        remaining = 3-days_since
                        reopen = (end+timedelta(days=3)).strftime('%d %b %Y')
                        flash(f'Staff ini baru resign pada {end.strftime("%d %b %Y")}. Pendaftaran ulang baru bisa dilakukan setelah {reopen}. Sisa {remaining} hari.','error')
                        return redirect(url_for('add_staff'))
                flash(f'KTP ini sudah terdaftar atas nama {existing["full_name"]} ({existing["emp_id"]}).','warning')
                return redirect(url_for('view_staff',staff_id=existing['id']))

            emp_id = gen_emp_id()
            db.execute("""INSERT INTO staff
                (emp_id,full_name,ktp_number,birth_date,birth_place,gender,religion,
                 address,rt_rw,kelurahan,kecamatan,kota,provinsi,
                 phone,position,department,education,
                 emergency_contact,emergency_relationship,emergency_phone,created_by)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (emp_id,request.form['full_name'],ktp,
                 request.form['birth_date'],request.form.get('birth_place',''),request.form['gender'],request.form['religion'],
                 request.form['address'],request.form['rt_rw'],
                 request.form['kelurahan'],request.form['kecamatan'],
                 request.form['kota'],request.form['provinsi'],
                 request.form['phone'],request.form['position'],request.form['department'],
                 request.form['education'],
                 request.form['emergency_contact'],request.form['emergency_relationship'],
                 request.form['emergency_phone'],session['user']))
            staff_id = db.fetchone("SELECT id FROM staff WHERE emp_id=?", (emp_id,))['id']
            st = request.form['staff_type']
            sd = request.form['start_date']
            ce = request.form.get('contract_end_date') if st=='PKWT' else \
                 (datetime.strptime(sd,'%Y-%m-%d')+timedelta(days=90)).strftime('%Y-%m-%d')
            db.execute("""INSERT INTO employment_periods
                (staff_id,period_number,staff_type,start_date,contract_end_date,sponsor_name,created_by)
                VALUES (?,1,?,?,?,?,?)""",
                (staff_id,st,sd,ce,request.form.get('sponsor_name',''),session['user']))
            db.commit()
            log_audit('ADD_STAFF','staff',staff_id,f"Tambah: {request.form['full_name']} ({emp_id})")
        flash(f'Karyawan {request.form["full_name"]} berhasil ditambahkan. ID: {emp_id}','success')
        return redirect(url_for('view_staff',staff_id=staff_id))
    # Check if coming from hasil tes (auto-fill)
    prefill = {}
    import_result_id = session.pop('import_from_tes', None)
    if import_result_id:
        with get_db() as db:
            pelamar = db.fetchone("SELECT * FROM data_pelamar WHERE result_id=?", (import_result_id,))
            result  = db.fetchone("SELECT * FROM test_results WHERE id=?", (import_result_id,))
        if pelamar:
            # Parse darurat for emergency contact
            import json as _json
            darurat = []
            try: darurat = _json.loads(pelamar.get('darurat_json') or '[]')
            except: pass
            first_darurat = darurat[0] if darurat else {}
            prefill = {
                'full_name':               pelamar.get('nama_lengkap') or (result.get('nama_lengkap') if result else ''),
                'ktp_number':              pelamar.get('nik') or (result.get('nik') if result else ''),
                'birth_date':              pelamar.get('tanggal_lahir',''),
                'birth_place':             pelamar.get('tempat_lahir',''),
                'gender':                  pelamar.get('jenis_kelamin',''),
                'religion':                pelamar.get('agama',''),
                'address':                 pelamar.get('alamat_tinggal',''),
                'phone':                   pelamar.get('no_hp',''),
                'emergency_contact':       first_darurat.get('nama',''),
                'emergency_relationship':  first_darurat.get('hubungan',''),
                'emergency_phone':         first_darurat.get('telepon',''),
                'position':                result.get('posisi','') if result else '',
                'import_result_id':        import_result_id,
            }
            flash(f'Data {prefill["full_name"]} berhasil diimport dari hasil tes. Harap periksa semua data sebelum menyimpan.', 'warning')
    return render_template('add_staff.html', departments=DEPARTMENTS_POSITIONS,
                          provinces=PROVINCES, religions=RELIGIONS, prefill=prefill)

@app.route('/staff/<int:staff_id>')
@login_required
def view_staff(staff_id):
    with get_db() as db:
        staff         = db.fetchone("SELECT * FROM staff WHERE id=?", (staff_id,))
        periods       = db.fetchall("SELECT * FROM employment_periods WHERE staff_id=? ORDER BY period_number DESC",(staff_id,))
        active_period = db.fetchone("SELECT * FROM employment_periods WHERE staff_id=? AND status='AKTIF'", (staff_id,))
        discipline    = db.fetchall("""SELECT dr.*,ep.period_number FROM discipline_records dr
                                      JOIN employment_periods ep ON dr.period_id=ep.id
                                      WHERE dr.staff_id=? ORDER BY dr.incident_date DESC""", (staff_id,))
        documents     = db.fetchall("SELECT * FROM documents WHERE staff_id=? ORDER BY created_at DESC", (staff_id,))
    if not staff:
        flash('Karyawan tidak ditemukan.','error')
        return redirect(url_for('staff_list'))

    days_left = None
    if active_period and active_period['contract_end_date']:
        end = datetime.strptime(active_period['contract_end_date'],'%Y-%m-%d').date()
        days_left = (end-date.today()).days

    pkwt_total_days = get_pkwt_total_days(staff_id) if active_period and active_period['staff_type']=='PKWT' else 0
    pkwt_years = round(pkwt_total_days/365,1)

    have_codes = [d['doc_code'] for d in documents]+[d['doc_code'] for d in discipline]

    bpjs_eligible = False
    if active_period:
        start = datetime.strptime(active_period['start_date'],'%Y-%m-%d').date()
        bpjs_eligible = (date.today()-start).days >= 365

    return render_template('view_staff.html', staff=staff, periods=periods,
                          active_period=active_period, discipline=discipline,
                          documents=documents, days_left=days_left,
                          discipline_types=DISCIPLINE_TYPES, doc_types=DOC_TYPES,
                          exit_reasons=EXIT_REASONS, have_codes=have_codes,
                          dp_checklist=DP_CHECKLIST,
                          is_head_or_owner=is_head_or_owner(), is_owner=is_owner(),
                          pkwt_total_days=pkwt_total_days, pkwt_years=pkwt_years,
                          bpjs_eligible=bpjs_eligible)

@app.route('/staff/<int:staff_id>/edit', methods=['GET','POST'])
@login_required
@role_required('hr_head','owner')
def edit_staff(staff_id):
    with get_db() as db:
        staff = db.fetchone("SELECT * FROM staff WHERE id=?", (staff_id,))
    if not staff: return redirect(url_for('staff_list'))
    if request.method == 'POST':
        with get_db() as db:
            db.execute("""UPDATE staff SET full_name=?,birth_date=?,birth_place=?,gender=?,religion=?,
                         address=?,rt_rw=?,kelurahan=?,kecamatan=?,kota=?,provinsi=?,
                         phone=?,position=?,department=?,education=?,
                         emergency_contact=?,emergency_relationship=?,emergency_phone=?,
                         updated_by=?,updated_at=datetime('now','localtime') WHERE id=?""",
                      (request.form['full_name'],request.form['birth_date'],request.form.get('birth_place',''),request.form['gender'],
                       request.form['religion'],request.form['address'],request.form['rt_rw'],
                       request.form['kelurahan'],request.form['kecamatan'],request.form['kota'],
                       request.form['provinsi'],request.form['phone'],request.form['position'],
                       request.form['department'],request.form['education'],
                       request.form['emergency_contact'],request.form['emergency_relationship'],
                       request.form['emergency_phone'],session['user'],staff_id))
            db.commit()
            log_audit('EDIT_STAFF','staff',staff_id,f"Edit: {staff['full_name']}")
        flash('Data diperbarui.','success')
        return redirect(url_for('view_staff',staff_id=staff_id))
    return render_template('edit_staff.html',staff=staff,
                          departments=DEPARTMENTS_POSITIONS,provinces=PROVINCES,religions=RELIGIONS)

@app.route('/staff/<int:staff_id>/add_discipline', methods=['POST'])
@login_required
def add_discipline(staff_id):
    with get_db() as db:
        staff  = db.fetchone("SELECT * FROM staff WHERE id=?", (staff_id,))
        period = db.fetchone("SELECT * FROM employment_periods WHERE staff_id=? AND status='AKTIF'", (staff_id,))
        if not period:
            flash('Tidak ada periode kerja aktif.','error')
            return redirect(url_for('view_staff',staff_id=staff_id))
        sp_type = request.form['sp_type']
        code    = DISCIPLINE_TYPES[sp_type]['code']
        doc_ref = gen_doc_ref(staff['emp_id'],code)
        db.execute("""INSERT INTO discipline_records
            (staff_id,period_id,sp_type,doc_code,incident_date,description,doc_ref,created_by)
            VALUES (?,?,?,?,?,?,?,?)""",
            (staff_id,period['id'],sp_type,code,
             request.form['incident_date'],request.form['description'],doc_ref,session['user']))
        db.commit()
        log_audit('ADD_DISCIPLINE','discipline_records',staff_id,
                 f"{sp_type} — {staff['full_name']}")
    flash(f'Catatan disiplin ditambahkan. Referensi: {doc_ref} — Tulis pada surat fisik.','success')
    return redirect(url_for('view_staff',staff_id=staff_id))

@app.route('/discipline/<int:disc_id>/update', methods=['POST'])
@login_required
def update_discipline(disc_id):
    with get_db() as db:
        disc = db.fetchone("SELECT * FROM discipline_records WHERE id=?", (disc_id,))
        drive = request.form.get('drive_path','').strip()
        phys  = request.form.get('physical_location','').strip()
        if drive:
            if not disc['drive_path'] or is_head_or_owner():
                db.execute("UPDATE discipline_records SET drive_path=? WHERE id=?",(drive,disc_id))
            else:
                flash('Link Drive terkunci. Hubungi HR Head.','error')
                return redirect(url_for('view_staff',staff_id=disc['staff_id']))
        if phys:
            if not disc['physical_location'] or is_head_or_owner():
                db.execute("UPDATE discipline_records SET physical_location=? WHERE id=?",(phys,disc_id))
            else:
                flash('Lokasi fisik sudah diisi. Hubungi HR Head.','error')
                return redirect(url_for('view_staff',staff_id=disc['staff_id']))
        db.commit()
        log_audit('UPDATE_DISCIPLINE','discipline_records',disc_id,f"Drive:{drive}|Fisik:{phys}")
    flash('Diperbarui.','success')
    return redirect(url_for('view_staff',staff_id=disc['staff_id']))

@app.route('/staff/<int:staff_id>/add_doc', methods=['POST'])
@login_required
def add_doc(staff_id):
    with get_db() as db:
        staff    = db.fetchone("SELECT * FROM staff WHERE id=?", (staff_id,))
        doc_type = request.form['doc_type']
        info     = DOC_TYPES[doc_type]
        code     = info['code']
        doc_ref  = gen_doc_ref(staff['emp_id'],code)
        dp_check = json.dumps(request.form.getlist('dp_items')) if code=='DP' else None
        dp_other = request.form.get('dp_others','').strip() if code=='DP' else None
        db.execute("""INSERT INTO documents
            (staff_id,doc_type,doc_code,doc_ref,description,reason,
             dp_checklist,dp_others,drive_path,physical_location,need_drive,created_by)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (staff_id,doc_type,code,doc_ref,
             request.form.get('description',''),request.form.get('reason',''),
             dp_check,dp_other,
             request.form.get('drive_path','') or None,
             request.form.get('physical_location','') or None,
             1 if info['need_drive'] else 0,session['user']))
        db.commit()
        log_audit('ADD_DOCUMENT','documents',staff_id,f"{doc_type} — {staff['full_name']} — {doc_ref}")
    flash(f'Dokumen ditambahkan. Referensi: {doc_ref} — Tulis pada dokumen fisik dan nama file di Google Drive.','success')
    return redirect(url_for('view_staff',staff_id=staff_id))

@app.route('/document/<int:doc_id>/update', methods=['POST'])
@login_required
def update_doc(doc_id):
    with get_db() as db:
        doc   = db.fetchone("SELECT * FROM documents WHERE id=?", (doc_id,))
        drive = request.form.get('drive_path','').strip()
        phys  = request.form.get('physical_location','').strip()
        if drive:
            if not doc['drive_path'] or is_head_or_owner():
                db.execute("UPDATE documents SET drive_path=? WHERE id=?",(drive,doc_id))
            else:
                flash('Link Drive terkunci. Hubungi HR Head.','error')
                return redirect(url_for('view_staff',staff_id=doc['staff_id']))
        if phys:
            if not doc['physical_location'] or is_head_or_owner():
                db.execute("UPDATE documents SET physical_location=? WHERE id=?",(phys,doc_id))
            else:
                flash('Lokasi fisik sudah diisi. Hubungi HR Head.','error')
                return redirect(url_for('view_staff',staff_id=doc['staff_id']))
        db.commit()
        log_audit('UPDATE_DOC','documents',doc_id,f"Drive:{drive}|Fisik:{phys}")
    flash('Diperbarui.','success')
    return redirect(url_for('view_staff',staff_id=doc['staff_id']))

@app.route('/staff/<int:staff_id>/renew', methods=['POST'])
@login_required
@role_required('hr_head','owner')
def renew_contract(staff_id):
    with get_db() as db:
        period = db.fetchone("SELECT * FROM employment_periods WHERE staff_id=? AND status='AKTIF'", (staff_id,))
        staff  = db.fetchone("SELECT * FROM staff WHERE id=?", (staff_id,))
        result    = request.form['evaluation_result']
        notes     = request.form.get('evaluation_notes','')
        salary    = request.form.get('salary_increase','')
        bpjs      = 1 if request.form.get('bpjs_enrolled')=='yes' else 0
        new_start = request.form['new_start_date']
        new_type  = 'PKWT' if result=='Naik PKWT' else period['staff_type']
        ce = request.form.get('new_contract_end') if result=='Naik PKWT' else \
             (datetime.strptime(new_start,'%Y-%m-%d')+timedelta(days=90)).strftime('%Y-%m-%d')
        db.execute("""UPDATE employment_periods SET status='SELESAI',end_date=?,
                     evaluation_result=?,evaluation_notes=?,salary_increase=?,bpjs_enrolled=?
                     WHERE id=?""", (new_start,result,notes,salary,bpjs,period['id']))
        db.execute("""INSERT INTO employment_periods
            (staff_id,period_number,staff_type,start_date,contract_end_date,sponsor_name,created_by)
            VALUES (?,?,?,?,?,?,?)""",
            (staff_id,period['period_number']+1,new_type,new_start,ce,period['sponsor_name'],session['user']))
        db.commit()
        log_audit('RENEW_CONTRACT','employment_periods',staff_id,
                 f"Hasil:{result}|Gaji:{salary}|BPJS:{'Ya' if bpjs else 'Tidak'}")
    flash(f'Kontrak {staff["full_name"]} diperbarui.','success')
    return redirect(url_for('view_staff',staff_id=staff_id))

@app.route('/staff/<int:staff_id>/exit', methods=['POST'])
@login_required
def exit_staff(staff_id):
    with get_db() as db:
        period    = db.fetchone("SELECT * FROM employment_periods WHERE staff_id=? AND status='AKTIF'", (staff_id,))
        staff     = db.fetchone("SELECT * FROM staff WHERE id=?", (staff_id,))
        end_date  = request.form['end_date']
        end_reason= request.form['end_reason']
        blacklist = request.form.get('blacklist')=='yes'
        bl_reason = request.form.get('blacklist_reason','')
        db.execute("UPDATE employment_periods SET status='SELESAI',end_date=?,end_reason=? WHERE id=?",
                  (end_date,end_reason,period['id']))
        db.execute("""UPDATE staff SET status='TIDAK_AKTIF',is_blacklisted=?,blacklist_reason=?,
                     updated_by=?,updated_at=datetime('now','localtime') WHERE id=?""",
                  (1 if blacklist else 0,bl_reason if blacklist else None,session['user'],staff_id))
        db.commit()
        log_audit('EXIT_STAFF','staff',staff_id,f"Keluar:{end_reason}|BL:{'Ya' if blacklist else 'Tidak'}")
    flash(f'{staff["full_name"]} diproses keluar.','success')
    return redirect(url_for('view_staff',staff_id=staff_id))

@app.route('/staff/<int:staff_id>/return', methods=['POST'])
@login_required
@role_required('hr_head','owner')
def return_to_work(staff_id):
    with get_db() as db:
        staff = db.fetchone("SELECT * FROM staff WHERE id=?", (staff_id,))
        if staff['is_blacklisted'] and not is_owner():
            flash('Staff ini diblacklist. Hanya Owner yang bisa memproses.','error')
            return redirect(url_for('view_staff',staff_id=staff_id))
        last  = db.fetchone("SELECT MAX(period_number) as m FROM employment_periods WHERE staff_id=?", (staff_id,))
        new_p = (last['m'] or 0)+1
        st = request.form['staff_type']
        sd = request.form['start_date']
        ce = request.form.get('contract_end_date') if st=='PKWT' else \
             (datetime.strptime(sd,'%Y-%m-%d')+timedelta(days=90)).strftime('%Y-%m-%d')
        db.execute("""INSERT INTO employment_periods
            (staff_id,period_number,staff_type,start_date,contract_end_date,sponsor_name,created_by)
            VALUES (?,?,?,?,?,?,?)""",
            (staff_id,new_p,st,sd,ce,request.form.get('sponsor_name',''),session['user']))
        db.execute("""UPDATE staff SET status='AKTIF',is_blacklisted=0,blacklist_reason=NULL,
                     updated_by=?,updated_at=datetime('now','localtime') WHERE id=?""",
                  (session['user'],staff_id))
        db.commit()
        log_audit('RETURN_TO_WORK','staff',staff_id,f"Periode {new_p} mulai {sd}")
    flash(f'{staff["full_name"]} kembali bekerja.','success')
    return redirect(url_for('view_staff',staff_id=staff_id))

@app.route('/sponsors')
@login_required
@role_required('hr_head','owner')
def sponsors():
    with get_db() as db:
        rows = db.fetchall("""SELECT ep.sponsor_name,s.full_name,s.emp_id,s.department,
                                    s.id as staff_id,ep.start_date,ep.status as ep_status,s.status as s_status
                             FROM employment_periods ep JOIN staff s ON ep.staff_id=s.id
                             WHERE ep.sponsor_name IS NOT NULL AND ep.sponsor_name!=''
                             AND ep.staff_type='HL-Outsource'
                             ORDER BY ep.sponsor_name,ep.start_date DESC""")
    from collections import defaultdict
    sponsor_map = defaultdict(list)
    for r in rows: sponsor_map[r['sponsor_name']].append(r)
    return render_template('sponsors.html', sponsor_map=dict(sponsor_map))

@app.route('/audit')
@login_required
@role_required('owner')
def audit_log():
    filter_role = request.args.get('role','')
    with get_db() as db:
        q = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        if filter_role: q += " AND role=?"; params.append(filter_role)
        q += " ORDER BY created_at DESC LIMIT 300"
        logs = db.fetchall(q,params)
    return render_template('audit_log.html', logs=logs, filter_role=filter_role)

@app.route('/users')
@login_required
@role_required('owner')
def user_list():
    with get_db() as db:
        users = db.fetchall("SELECT * FROM users ORDER BY role,username")
    return render_template('user_list.html', users=users)

@app.route('/users/add', methods=['GET','POST'])
@login_required
@role_required('owner')
def add_user():
    if request.method == 'POST':
        pw = hashlib.sha256(request.form['password'].encode()).hexdigest()
        try:
            with get_db() as db:
                db.execute("INSERT INTO users (username,password,full_name,role) VALUES (?,?,?,?)",
                          (request.form['username'],pw,request.form['full_name'],request.form['role']))
                db.commit()
                log_audit('ADD_USER','users',None,f"Tambah: {request.form['username']}")
            flash('User berhasil ditambahkan.','success')
            return redirect(url_for('user_list'))
        except: flash('Username sudah digunakan.','error')
    return render_template('add_user.html')

@app.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@role_required('owner')
def delete_user(user_id):
    with get_db() as db:
        user = db.fetchone("SELECT * FROM users WHERE id=?", (user_id,))
        if user['username'] == session['user']:
            flash('Tidak bisa menghapus akun sendiri.','error')
            return redirect(url_for('user_list'))
        db.execute("DELETE FROM users WHERE id=?",(user_id,))
        db.commit()
        log_audit('DELETE_USER','users',user_id,f"Hapus: {user['username']}")
    flash(f'User {user["username"]} berhasil dihapus.','success')
    return redirect(url_for('user_list'))

@app.route('/users/<int:user_id>/reset_password', methods=['POST'])
@login_required
@role_required('owner')
def reset_password(user_id):
    pw = hashlib.sha256(request.form['new_password'].encode()).hexdigest()
    with get_db() as db:
        user = db.fetchone("SELECT * FROM users WHERE id=?", (user_id,))
        db.execute("UPDATE users SET password=? WHERE id=?",(pw,user_id))
        db.commit()
        log_audit('RESET_PASSWORD','users',user_id,f"Reset: {user['username']}")
    flash('Password direset.','success')
    return redirect(url_for('user_list'))

@app.route('/api/check_ktp')
@login_required
def check_ktp():
    ktp = request.args.get('ktp','')
    with get_db() as db:
        e = db.fetchone("SELECT * FROM staff WHERE ktp_number=?", (ktp,))
    if e:
        block_msg = None
        with get_db() as db:
            last = db.fetchone("SELECT * FROM employment_periods WHERE staff_id=? ORDER BY id DESC LIMIT 1", (e['id'],))
        if last and last['end_date']:
            end = datetime.strptime(last['end_date'],'%Y-%m-%d').date()
            days_since = (date.today()-end).days
            if days_since < 3:
                remaining = 3-days_since
                block_msg = f"Baru resign {end.strftime('%d %b %Y')}. Bisa daftar ulang dalam {remaining} hari lagi."
        return jsonify({'found':True,'name':e['full_name'],'emp_id':e['emp_id'],
                       'status':e['status'],'blacklisted':bool(e['is_blacklisted']),
                       'blacklist_reason':e['blacklist_reason'],'staff_id':e['id'],
                       'block_msg':block_msg})
    return jsonify({'found':False})

@app.route('/api/positions')
@login_required
def get_positions():
    return jsonify(DEPARTMENTS_POSITIONS.get(request.args.get('dept',''),[]))

@app.route('/api/exit_docs')
@login_required
def get_exit_docs():
    return jsonify(EXIT_REASONS.get(request.args.get('reason',''),{}).get('docs',[]))

# Initialize DB only if tables don't exist yet (safe on redeploy)
def safe_init_db():
    try:
        with get_db() as db:
            count = db.fetchval("SELECT COUNT(*) FROM users")
            if count and count > 0:
                print("Database already initialized — skipping init_db()")
                return
    except:
        pass
    try:
        init_db()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Warning: init_db error: {e}")



# ── TES KANDIDAT — routes to append to app.py ─────────────────────────────────
# Add these imports to the top of app.py:
#   import random, string
# Add init_test_tables() call inside safe_init_db() or at app startup.

import random, string

# ── Question Bank ──────────────────────────────────────────────────────────────

# Colour codes and lot codes used at MKT for accuracy questions
# Each item: (code_a, code_b, is_same)
ACCURACY_PAIRS = {
    'operator': [
        ('MKT602260004787A', 'MKT602260004787A', True),
        ('MKT602260004787A', 'MKT60226004787A',  False),  # missing zero
        ('MKT501150003214B', 'MKT501150003214B', True),
        ('MKT501150003214B', 'MKT501150003241B', False),  # digits swapped
        ('P1318C26281025',   'P1316C26281025',   False),  # 8->6
        ('P1318C26281025',   'P1318C26281025',   True),
        ('P2204A18530612',   'P2204A18530612',   True),
        ('P2204A18530612',   'P2204A18530162',   False),  # digits swapped
        ('MKT703370008851C', 'MKT703370008851C', True),
        ('MKT703370008851C', 'MKT703370008815C', False),  # 51->15
        ('P0917B30042761',   'P0917B30042761',   True),
        ('P0917B30042761',   'P0917B30042716',   False),  # last digits swapped
        ('MKT408440006623A', 'MKT408440006623A', True),
        ('MKT408440006623A', 'MKT408440006632A', False),  # 23->32
        ('P1531D44187203',   'P1531D44187203',   True),
        ('P1531D44187203',   'P1531D44182703',   False),  # middle swap
        ('MKT119920001045B', 'MKT119920001045B', True),
        ('MKT119920001045B', 'MKT11992001045B',  False),  # missing zero
        ('P0623E55291804',   'P0623E55291804',   True),
        ('P0623E55291804',   'P0623E55219804',   False),  # 91->19
    ],
    'staff': [
        ('MKT602260004787A', 'MKT60226004787A',  False),
        ('MKT501150003214B', 'MKT501150003214B', True),
        ('P1318C26281025',   'P1316C2861025',    False),  # two differences
        ('MKT703370008851C', 'MKT703370008851C', True),
        ('P2204A18530612',   'P2204A18350612',   False),
        ('MKT408440006623A', 'MKT408440006623A', True),
        ('P1531D44187203',   'P1531D44187203',   True),
        ('MKT119920001045B', 'MKT119920001054B', False),
        ('P0623E55291804',   'P0623E55291804',   True),
        ('MKT305530007792D', 'MKT305530007972D', False),
        ('P0812F66304517',   'P0812F66304517',   True),
        ('MKT204420005561B', 'MKT204420005561B', True),
        ('P1109G77415628',   'P1109G77415682',   False),
        ('MKT901810009934C', 'MKT901810009934C', True),
        ('P0716H88526739',   'P0761H88526739',   False),
        ('MKT607670004478A', 'MKT607670004478A', True),
        ('P1423I99637840',   'P1423I99637840',   True),
        ('MKT803880006695D', 'MKT803880006965D', False),
        ('P0520J10748951',   'P0520J10748951',   True),
        ('MKT412250008823B', 'MKT412250008823B', True),
    ],
    'admin': [
        ('MKT602260004787A', 'MKT60226004787A',  False),
        ('P1318C26281025',   'P1316C2861025',    False),
        ('MKT501150003214B', 'MKT501150003214B', True),
        ('P2204A18530612',   'P2240A18530612',   False),
        ('MKT703370008851C', 'MKT703370008851C', True),
        ('P1531D44187203',   'P1531D44187203',   True),
        ('MKT408440006623A', 'MKT408440006632A', False),
        ('P0623E55291804',   'P0623E55219804',   False),
        ('MKT119920001045B', 'MKT119920001045B', True),
        ('P0812F66304517',   'P0812F66304517',   True),
        ('MKT305530007792D', 'MKT305530007792D', True),
        ('P1109G77415628',   'P1109G77415682',   False),
        ('MKT901810009934C', 'MKT901910009934C', False),
        ('P0716H88526739',   'P0716H88526739',   True),
        ('MKT607670004478A', 'MKT607670004478A', True),
        ('P1423I99637840',   'P1432I99637840',   False),
        ('MKT803880006695D', 'MKT803880006695D', True),
        ('P0520J10748951',   'P0520J10784951',   False),
        ('MKT412250008823B', 'MKT412250008823B', True),
        ('P1317K21859062',   'P1317K21859062',   True),
    ]
}

MATH_QUESTIONS = {
    'operator': [
        {
            'q': 'Target produksi hari ini adalah 480 unit dalam 8 jam kerja. Berapa unit yang harus diproduksi per jam?',
            'opts': ['50 unit', '60 unit', '55 unit', '65 unit'], 'ans': 1
        },
        {
            'q': 'Untuk membuat 1 roll kain dibutuhkan 4,5 kg benang. Berapa kg benang yang dibutuhkan untuk 8 roll?',
            'opts': ['32 kg', '36 kg', '38 kg', '40 kg'], 'ans': 1
        },
        {
            'q': 'Stok karton di gudang: 200 buah. Diambil 75 buah untuk packing. Berapa karton yang tersisa?',
            'opts': ['115', '125', '135', '120'], 'ans': 1
        },
        {
            'q': 'Seorang operator mengemas 48 produk per jam. Berapa produk yang dikemas dalam 6 jam?',
            'opts': ['268', '288', '278', '258'], 'ans': 1
        },
        {
            'q': 'Dalam 1 hari ada 2 shift kerja, masing-masing 8 jam. Mesin berhenti 30 menit per pergantian shift. Berapa jam total mesin beroperasi dalam sehari?',
            'opts': ['14,5 jam', '15 jam', '15,5 jam', '16 jam'], 'ans': 2
        },
        {
            'q': 'Satu bal kain berisi 50 meter. Ada 12 bal kain di gudang. Berapa meter total kain?',
            'opts': ['550 m', '600 m', '580 m', '620 m'], 'ans': 1
        },
        {
            'q': 'Mesin A memproduksi 90 unit per jam. Target hari ini 720 unit. Berapa jam mesin harus beroperasi?',
            'opts': ['6 jam', '7 jam', '8 jam', '9 jam'], 'ans': 2
        },
        {
            'q': 'Masuk gudang: 350 kg benang. Keluar: 120 kg. Rusak: 15 kg. Berapa kg benang yang masih bisa digunakan?',
            'opts': ['200 kg', '210 kg', '215 kg', '220 kg'], 'ans': 2
        },
        {
            'q': 'Satu karton berisi 24 potong kain. Ada 15 karton siap kirim. Berapa total potong kain?',
            'opts': ['320', '340', '360', '380'], 'ans': 2
        },
        {
            'q': 'Target mingguan: 2.400 unit dalam 6 hari kerja. Berapa unit target per hari?',
            'opts': ['350', '380', '400', '420'], 'ans': 2
        },
    
                {'q': 'Seorang karyawan mendapat upah Rp 80.000 per hari. Berapa upahnya dalam 26 hari kerja?', 'opts': ['Rp 1.900.000', 'Rp 2.000.000', 'Rp 2.080.000', 'Rp 2.100.000'], 'ans': 2},
        {'q': 'Sebuah mesin menghasilkan 45 meter kain per jam. Berapa meter kain yang dihasilkan dalam 7 jam?', 'opts': ['295 m', 'Rp 305 m', '315 m', '325 m'], 'ans': 2},
        {'q': 'Ada 3 kotak berisi masing-masing 24 gulungan benang. Berapa total gulungan benang?', 'opts': ['60', '66', '72', '78'], 'ans': 2},
        {'q': 'Dari 120 produk yang diperiksa, 6 produk cacat. Berapa persen produk yang tidak cacat?', 'opts': ['92%', '93%', '94%', '95%'], 'ans': 3},
        {'q': 'Stok awal: 500 meter. Masuk: 300 meter. Keluar: 420 meter. Berapa stok akhir?', 'opts': ['360 m', '370 m', '380 m', '390 m'], 'ans': 2},
        {'q': 'Mesin beroperasi 6 jam menghasilkan 540 unit. Berapa unit per jam?', 'opts': ['80', '85', '90', '95'], 'ans': 2},
        {'q': 'Dalam 1 minggu (5 hari kerja) target 1.000 unit. Sudah tercapai 650 unit dalam 3 hari. Berapa target sisa 2 hari?', 'opts': ['300', '320', '340', '350'], 'ans': 3},
        {'q': 'Benang 1 kg bisa membuat 8 meter kain. Berapa kg benang untuk 56 meter kain?', 'opts': ['6 kg', '7 kg', '8 kg', '9 kg'], 'ans': 1},
        {'q': 'Lembur 2 jam per hari selama 5 hari. Upah lembur Rp 15.000/jam. Berapa total upah lembur?', 'opts': ['Rp 130.000', 'Rp 140.000', 'Rp 150.000', 'Rp 160.000'], 'ans': 2},
        {'q': 'Sebuah karton berisi 30 potong kain. Jika ada 8 karton penuh dan 1 karton berisi 15 potong, berapa total potong kain?', 'opts': ['245', '250', '255', '260'], 'ans': 2},
    ],
    'staff': [
        {
            'q': 'Target produksi minggu ini: 3.600 unit dalam 6 hari kerja, 8 jam per hari. Berapa unit per jam yang harus dicapai?',
            'opts': ['70 unit', '75 unit', '80 unit', '85 unit'], 'ans': 1
        },
        {
            'q': 'Realisasi produksi bulan ini: 11.800 unit. Target: 12.500 unit. Berapa persen pencapaian?',
            'opts': ['92,4%', '94,4%', '95,4%', '93,4%'], 'ans': 1
        },
        {
            'q': 'Dari 500 meter kain yang diproduksi, 25 meter dinyatakan cacat. Berapa persen tingkat cacat?',
            'opts': ['4%', '5%', '6%', '7%'], 'ans': 1
        },
        {
            'q': 'Order masuk: 8.000 meter kain. Stok tersedia: 3.200 meter. Bahan baku untuk 1 meter membutuhkan 1,2 kg benang. Berapa kg benang yang masih dibutuhkan?',
            'opts': ['5.520 kg', '5.760 kg', '5.640 kg', '5.800 kg'], 'ans': 0
        },
        {
            'q': 'Kapasitas mesin: 150 unit per jam. Dalam 8 jam kerja ada 2 kali berhenti masing-masing 15 menit. Berapa total unit yang bisa diproduksi?',
            'opts': ['1.125 unit', '1.150 unit', '1.200 unit', '1.050 unit'], 'ans': 0
        },
        {
            'q': 'Produksi bulan lalu: 12.400 unit. Bulan ini naik 15%. Berapa produksi bulan ini?',
            'opts': ['13.860 unit', '14.260 unit', '14.060 unit', '13.660 unit'], 'ans': 0
        },
        {
            'q': 'Satu order membutuhkan 2,5 kg benang per meter kain. Order sebesar 400 meter. Stok benang tersedia 850 kg. Apakah stok cukup? Jika tidak, berapa kg kekurangannya?',
            'opts': ['Cukup, sisa 150 kg', 'Kurang 50 kg', 'Kurang 150 kg', 'Cukup, sisa 50 kg'], 'ans': 1
        },
        {
            'q': 'Mesin B mampu menghasilkan 200 meter kain per jam. Target order: 3.000 meter. Berapa hari kerja (8 jam/hari) yang dibutuhkan?',
            'opts': ['1,5 hari', '2 hari', '1,875 hari', '2,5 hari'], 'ans': 2
        },
        {
            'q': 'Dari 240 karyawan, 30% adalah perempuan. Berapa jumlah karyawan laki-laki?',
            'opts': ['72', '148', '168', '160'], 'ans': 2
        },
        {
            'q': 'Reject rate target maksimal 3%. Produksi hari ini 850 unit, reject 30 unit. Apakah target tercapai?',
            'opts': ['Ya, reject rate 3,0%', 'Tidak, reject rate 3,53%', 'Ya, reject rate 2,8%', 'Tidak, reject rate 4,0%'], 'ans': 1
        },
    
                {'q': 'Efisiensi mesin bulan ini 87%. Target minimal 85%. Jika kapasitas penuh 15.000 unit, berapa unit yang terproduksi?', 'opts': ['12.750 unit', '13.000 unit', '13.050 unit', '13.500 unit'], 'ans': 2},
        {'q': 'Gaji pokok Rp 4.500.000. Tunjangan transport Rp 300.000. Tunjangan makan Rp 450.000. Dipotong BPJS 1% dari gaji pokok. Berapa take-home pay?', 'opts': ['Rp 5.150.000', 'Rp 5.175.000', 'Rp 5.200.000', 'Rp 5.205.000'], 'ans': 1},
        {'q': 'Produksi 3 shift: Shift 1 = 2.400 unit, Shift 2 = 2.100 unit, Shift 3 = 1.950 unit. Berapa rata-rata produksi per shift?', 'opts': ['2.100 unit', '2.150 unit', '2.200 unit', '2.250 unit'], 'ans': 1},
        {'q': 'Target harian 800 unit. Hari Senin: 780, Selasa: 820, Rabu: 760. Berapa rata-rata pencapaian vs target?', 'opts': ['97%', '97,5%', '98%', '98,5%'], 'ans': 0},
        {'q': 'Stok benang 3 jenis: A=1.200 kg, B=850 kg, C=1.450 kg. Order membutuhkan masing-masing 400 kg. Jenis mana yang tidak cukup?', 'opts': ['Hanya B', 'Hanya A', 'B dan C', 'Semua cukup'], 'ans': 0},
        {'q': 'Mesin berjalan 22 hari dalam sebulan, 8 jam per hari. Downtime total 12 jam. Berapa persen availability mesin?', 'opts': ['91,8%', '92,5%', '93,2%', '93,8%'], 'ans': 2},
        {'q': 'Biaya produksi per unit: bahan Rp 12.000, tenaga Rp 5.000, overhead Rp 3.000. Harga jual Rp 25.000. Berapa margin per unit?', 'opts': ['Rp 4.000', 'Rp 5.000', 'Rp 6.000', 'Rp 7.000'], 'ans': 1},
        {'q': 'Dari 500 karyawan, 35% operator, 45% tenaga harian, sisanya staff. Berapa jumlah staff?', 'opts': ['90 orang', '95 orang', '100 orang', '105 orang'], 'ans': 2},
        {'q': 'Produksi bulan ini 14.500 unit. Reject 290 unit. Berapa persen yield (produk bagus)?', 'opts': ['97,5%', '98%', '98,5%', '99%'], 'ans': 1},
        {'q': 'Order: 6.000 meter kain dalam 12 hari kerja. 3 mesin masing-masing 180 m/hari. Apakah bisa selesai tepat waktu?', 'opts': ['Tidak, kurang 480 m', 'Ya, tepat 6.480 m', 'Ya, dengan sisa 480 m', 'Tidak, hanya 5.400 m'], 'ans': 2},
    ],
    'admin': [
        {
            'q': 'Satu order membutuhkan 120 meter kain per warna. Ada 4 warna. Stok tersedia 380 meter. Berapa meter kekurangannya?',
            'opts': ['80 meter', '100 meter', '60 meter', '40 meter'], 'ans': 0
        },
        {
            'q': 'Dari 5 hari kerja, seorang karyawan hadir 4 hari. Berapa persen tingkat kehadirannya?',
            'opts': ['75%', '80%', '85%', '90%'], 'ans': 1
        },
        {
            'q': 'Stok benang awal bulan: 2.500 kg. Masuk: 1.200 kg. Terpakai: 1.800 kg. Berapa stok akhir bulan?',
            'opts': ['1.800 kg', '1.900 kg', '2.000 kg', '1.700 kg'], 'ans': 1
        },
        {
            'q': 'Dalam sebulan ada 26 hari kerja. Karyawan A tidak masuk 4 hari. Berapa persen tingkat absensinya?',
            'opts': ['13,4%', '14,4%', '15,4%', '16,4%'], 'ans': 2
        },
        {
            'q': 'Order A: 500 meter @ 1,5 kg benang/meter. Order B: 300 meter @ 2 kg benang/meter. Berapa total benang yang dibutuhkan?',
            'opts': ['1.300 kg', '1.350 kg', '1.400 kg', '1.450 kg'], 'ans': 0
        },
        {
            'q': 'Kapasitas gudang: 5.000 unit. Saat ini terisi 3.750 unit. Berapa persen kapasitas yang sudah terpakai?',
            'opts': ['70%', '72%', '75%', '78%'], 'ans': 2
        },
        {
            'q': 'Reorder point: stok di bawah 500 kg. Stok saat ini: 380 kg. Order minimum: 1.000 kg. Apakah perlu order?',
            'opts': ['Tidak perlu', 'Perlu, order 620 kg', 'Perlu, order 1.000 kg', 'Perlu, order 500 kg'], 'ans': 2
        },
        {
            'q': 'Dari 3 mesin, mesin A produksi 200 m/hari, B produksi 150 m/hari, C produksi 180 m/hari. Berapa hari untuk selesaikan order 2.600 meter?',
            'opts': ['4 hari', '5 hari', '6 hari', '3 hari'], 'ans': 1
        },
        {
            'q': 'Jumlah karyawan aktif: 245. Karyawan hadir: 218. Berapa persen tingkat kehadiran hari ini?',
            'opts': ['87%', '88%', '89%', '90%'], 'ans': 2
        },
        {
            'q': 'Sisa kontrak karyawan: 45 hari. Hari ini tanggal 2 April 2026. Kapan kontrak berakhir?',
            'opts': ['15 Mei 2026', '16 Mei 2026', '17 Mei 2026', '18 Mei 2026'], 'ans': 2
        },
    
                {'q': 'Anggaran bulanan departemen: Rp 85.000.000. Sudah terpakai 62%. Berapa sisa anggaran?', 'opts': ['Rp 31.300.000', 'Rp 32.300.000', 'Rp 33.300.000', 'Rp 34.300.000'], 'ans': 1},
        {'q': 'Formula Excel: =COUNTIF(A1:A10,">100"). Ada 10 nilai: 95,110,87,105,120,98,115,88,102,99. Hasilnya?', 'opts': ['3', '4', '5', '6'], 'ans': 1},
        {'q': 'Karyawan A lembur 3 jam @ Rp 18.750/jam. Karyawan B lembur 5 jam @ Rp 15.000/jam. Total biaya lembur keduanya?', 'opts': ['Rp 131.250', 'Rp 131.500', 'Rp 131.750', 'Rp 132.000'], 'ans': 0},
        {'q': 'Laporan menunjukkan reject rate 3 bulan terakhir: 2,1%, 3,4%, 1,8%. Berapa rata-rata reject rate?', 'opts': ['2,3%', '2,4%', '2,43%', '2,5%'], 'ans': 2},
        {'q': 'Harga benang naik 8% dari Rp 45.000/kg. Kebutuhan bulan ini 1.200 kg. Berapa tambahan biaya dibanding bulan lalu?', 'opts': ['Rp 3.960.000', 'Rp 4.160.000', 'Rp 4.320.000', 'Rp 4.500.000'], 'ans': 2},
        {'q': 'Target rekrutmen: 20 karyawan. Sudah diinterview 35 kandidat, acceptance rate 40%. Berapa yang sudah diterima?', 'opts': ['12 orang', '14 orang', '15 orang', '16 orang'], 'ans': 1},
        {'q': 'Formula: =VLOOKUP(D2,A2:B10,2,FALSE). D2="MKT-001". Fungsi ini untuk?', 'opts': ['Menghitung jumlah', 'Mencari nilai berdasarkan kode', 'Mengurutkan data', 'Menghitung rata-rata'], 'ans': 1},
        {'q': 'Turnover karyawan: awal bulan 248 orang, keluar 12, masuk 8. Berapa turnover rate bulan ini?', 'opts': ['3,8%', '4,0%', '4,5%', '4,8%'], 'ans': 3},
        {'q': 'Data produksi: Min=1.800, Max=2.400, Rata-rata=2.100. Berapa range-nya?', 'opts': ['500', '550', '600', '650'], 'ans': 2},
        {'q': 'Biaya per karyawan per bulan: gaji Rp 3.800.000, BPJS perusahaan Rp 418.000, THR/12 Rp 316.667. Berapa total cost per karyawan?', 'opts': ['Rp 4.434.667', 'Rp 4.534.667', 'Rp 4.634.667', 'Rp 4.734.667'], 'ans': 1},
    ]
}

LOGIC_QUESTIONS = {
    'operator': [
        # Number sequences
        {'type': 'seq', 'q': 'Lanjutkan urutan: 2, 4, 6, 8, ...', 'opts': ['9', '10', '11', '12'], 'ans': 1},
        {'type': 'seq', 'q': 'Lanjutkan urutan: 5, 10, 15, 20, ...', 'opts': ['22', '24', '25', '30'], 'ans': 2},
        {'type': 'seq', 'q': 'Lanjutkan urutan: 1, 3, 5, 7, ...', 'opts': ['8', '9', '10', '11'], 'ans': 1},
        {'type': 'seq', 'q': 'Lanjutkan urutan: 100, 90, 80, 70, ...', 'opts': ['55', '60', '65', '50'], 'ans': 1},
        {'type': 'seq', 'q': 'Lanjutkan urutan: 3, 6, 9, 12, ...', 'opts': ['13', '14', '15', '16'], 'ans': 2},
        # Simple deduction
        {'type': 'logic', 'q': 'Semua produk yang lolos QC boleh dikirim. Produk A lolos QC. Maka produk A:', 'opts': ['Tidak boleh dikirim', 'Mungkin boleh dikirim', 'Boleh dikirim', 'Perlu dicek ulang'], 'ans': 2},
        {'type': 'logic', 'q': 'Mesin selalu berhenti jika tidak ada bahan baku. Saat ini tidak ada bahan baku. Maka mesin:', 'opts': ['Tetap jalan', 'Mungkin berhenti', 'Pasti berhenti', 'Butuh dicek'], 'ans': 2},
        {'type': 'logic', 'q': 'Shift pagi mulai jam 07.00, shift siang mulai 4 jam kemudian. Shift siang mulai jam:', 'opts': ['10.00', '11.00', '12.00', '13.00'], 'ans': 1},
        # Raven style (described in text for operator - simpler)
        {'type': 'matrix', 'q': 'Pola: Baris 1: ▲ ▲▲ ▲▲▲ | Baris 2: ■ ■■ ■■■ | Baris 3: ● ●● ?', 'opts': ['●', '●●●', '●●', '■■■'], 'ans': 1},
        {'type': 'matrix', 'q': 'Urutan gambar: kotak kecil → kotak sedang → kotak besar → kotak kecil → kotak sedang → ?', 'opts': ['kotak kecil', 'kotak besar', 'kotak sedang', 'lingkaran'], 'ans': 1},
    
                {'q': 'Lanjutkan urutan: 1, 2, 4, 8, ...', 'opts': ['12', '14', '16', '18'], 'ans': 2},
        {'q': 'Lanjutkan urutan: 50, 45, 40, 35, ...', 'opts': ['28', '29', '30', '31'], 'ans': 2},
        {'q': 'Semua karyawan harus pakai APD. Budi adalah karyawan. Maka Budi:', 'opts': ['Mungkin pakai APD', 'Tidak perlu APD', 'Harus pakai APD', 'Tergantung situasi'], 'ans': 2},
        {'q': 'Jika hari ini Senin, 3 hari lagi adalah hari apa?', 'opts': ['Rabu', 'Kamis', 'Jumat', 'Sabtu'], 'ans': 1},
        {'q': 'Pola: 1 kotak, 3 kotak, 5 kotak, 7 kotak, ... Berikutnya?', 'opts': ['8 kotak', '9 kotak', '10 kotak', '11 kotak'], 'ans': 1},
        {'q': 'Lanjutkan urutan: A, C, E, G, ...', 'opts': ['H', 'I', 'J', 'K'], 'ans': 1},
        {'q': 'Bahan baku datang setiap Senin. Hari ini Kamis. Berapa hari lagi bahan datang?', 'opts': ['3 hari', '4 hari', '5 hari', '6 hari'], 'ans': 0},
        {'q': 'Mesin A lebih baru dari mesin B. Mesin B lebih baru dari mesin C. Mesin mana yang paling lama?', 'opts': ['Mesin A', 'Mesin B', 'Mesin C', 'Tidak bisa ditentukan'], 'ans': 2},
        {'q': 'Lanjutkan pola: ○●○○●○○○●... Simbol ke-10 adalah?', 'opts': ['○', '●', '○○', '●●'], 'ans': 0},
        {'q': 'Gudang A lebih besar dari gudang B. Gudang C lebih kecil dari gudang B. Gudang mana paling kecil?', 'opts': ['A', 'B', 'C', 'Sama besar'], 'ans': 2},
    ],
    'staff': [
        # Number sequences (harder)
        {'type': 'seq', 'q': 'Lanjutkan urutan: 3, 6, 12, 24, ...', 'opts': ['36', '42', '48', '56'], 'ans': 2},
        {'type': 'seq', 'q': 'Lanjutkan urutan: 1, 4, 9, 16, ...', 'opts': ['20', '24', '25', '30'], 'ans': 2},
        {'type': 'seq', 'q': 'Lanjutkan urutan: 2, 5, 10, 17, 26, ...', 'opts': ['33', '35', '37', '40'], 'ans': 2},
        {'type': 'seq', 'q': 'Lanjutkan urutan: 100, 50, 25, 12.5, ...', 'opts': ['5', '6', '6.25', '7'], 'ans': 2},
        {'type': 'seq', 'q': 'Lanjutkan urutan: 1, 1, 2, 3, 5, 8, ...', 'opts': ['10', '11', '12', '13'], 'ans': 3},
        # Deduction
        {'type': 'logic', 'q': 'Jika semua pengawas wajib hadir rapat, dan Budi adalah pengawas, maka:', 'opts': ['Budi mungkin hadir rapat', 'Budi tidak wajib hadir', 'Budi wajib hadir rapat', 'Tidak bisa ditentukan'], 'ans': 2},
        {'type': 'logic', 'q': 'Semua produk reject tidak boleh dikirim. Produk X adalah reject. Produk Y bukan reject. Mana yang boleh dikirim?', 'opts': ['Produk X', 'Produk Y', 'Keduanya', 'Tidak ada'], 'ans': 1},
        {'type': 'logic', 'q': 'Mesin A lebih cepat dari mesin B. Mesin B lebih cepat dari mesin C. Mesin mana yang paling lambat?', 'opts': ['Mesin A', 'Mesin B', 'Mesin C', 'Tidak bisa ditentukan'], 'ans': 2},
        # Matrix (Raven style - SVG rendered)
        {'type': 'raven', 'q': 'Perhatikan pola matriks 3×3. Baris 1: ○ ○○ ○○○ | Baris 2: □ □□ □□□ | Baris 3: △ △△ ?', 'opts': ['○', '△△', '△△△', '□□□'], 'ans': 2},
        {'type': 'raven', 'q': 'Pola: setiap baris, bentuk bergerak dari kiri ke kanan. Baris 1: ■□□ | Baris 2: □■□ | Baris 3: ?', 'opts': ['■□□', '□□■', '□■□', '■■□'], 'ans': 1},
    
                {'q': 'Lanjutkan urutan: 2, 6, 18, 54, ...', 'opts': ['108', '144', '162', '180'], 'ans': 2},
        {'q': 'Lanjutkan urutan: 81, 27, 9, 3, ...', 'opts': ['0', '1', '2', '3'], 'ans': 1},
        {'q': 'Semua kepala shift wajib membuat laporan harian. Andi adalah kepala shift. Rudi bukan kepala shift. Siapa yang wajib membuat laporan?', 'opts': ['Rudi', 'Keduanya', 'Andi', 'Tidak ada'], 'ans': 2},
        {'q': 'Jika MESIN = 68, maka BENANG = ?', 'opts': ['56', '58', '60', '62'], 'ans': 2},
        {'q': 'Lanjutkan: AZ, BY, CX, DW, ...', 'opts': ['EV', 'EU', 'FV', 'EW'], 'ans': 0},
        {'q': 'Produk A lebih mahal dari B. B lebih mahal dari C. C lebih mahal dari D. Produk mana yang paling murah?', 'opts': ['A', 'B', 'C', 'D'], 'ans': 3},
        {'q': 'Jika semua supervisor punya laptop, dan tidak semua karyawan adalah supervisor, maka:', 'opts': ['Semua karyawan punya laptop', 'Tidak ada karyawan yang punya laptop', 'Beberapa karyawan mungkin tidak punya laptop', 'Supervisor tidak punya laptop'], 'ans': 2},
        {'q': 'Lanjutkan urutan: 7, 14, 28, 56, ...', 'opts': ['96', '102', '112', '128'], 'ans': 2},
        {'q': 'Dari pernyataan: "Tidak ada produk cacat yang lolos QC" — mana yang pasti benar?', 'opts': ['Semua produk lolos QC', 'Produk yang lolos QC pasti tidak cacat', 'Semua produk cacat', 'QC tidak efektif'], 'ans': 1},
        {'q': 'Shift kerja: Pagi 06.00-14.00, Siang 14.00-22.00, Malam 22.00-06.00. Jika masuk shift malam hari Senin pukul 22.00, selesai pada:', 'opts': ['Senin 06.00', 'Selasa 06.00', 'Selasa 22.00', 'Rabu 06.00'], 'ans': 1},
    ],
    'admin': [
        # Number sequences
        {'type': 'seq', 'q': 'Lanjutkan urutan: 3, 6, 12, 24, ...', 'opts': ['36', '42', '48', '56'], 'ans': 2},
        {'type': 'seq', 'q': 'Lanjutkan urutan: 1, 4, 9, 16, 25, ...', 'opts': ['30', '35', '36', '40'], 'ans': 2},
        {'type': 'seq', 'q': 'Lanjutkan urutan: 2, 5, 10, 17, 26, ...', 'opts': ['33', '35', '37', '40'], 'ans': 2},
        {'type': 'seq', 'q': 'Lanjutkan urutan: 1, 1, 2, 3, 5, 8, ...', 'opts': ['10', '11', '12', '13'], 'ans': 3},
        {'type': 'seq', 'q': 'Lanjutkan urutan: 512, 256, 128, 64, ...', 'opts': ['16', '24', '32', '48'], 'ans': 2},
        # Formula logic (admin only)
        {'type': 'logic', 'q': 'Formula Excel: =IF(C2>=70,"LULUS","TIDAK LULUS"). Nilai di C2 adalah 68. Hasilnya:', 'opts': ['LULUS', 'TIDAK LULUS', 'ERROR', '68'], 'ans': 1},
        {'type': 'logic', 'q': 'Formula: =SUM(A1:A5). Nilai A1=10, A2=20, A3=15, A4=25, A5=30. Hasilnya:', 'opts': ['90', '95', '100', '105'], 'ans': 2},
        {'type': 'logic', 'q': 'Formula: =AVERAGE(B1:B4). B1=80, B2=90, B3=70, B4=60. Hasilnya:', 'opts': ['72', '75', '78', '80'], 'ans': 1},
        {'type': 'logic', 'q': 'Formula: =IF(AND(A1>0,B1>0),"OK","TIDAK"). A1=5, B1=-3. Hasilnya:', 'opts': ['OK', 'TIDAK', 'ERROR', '5'], 'ans': 1},
        {'type': 'raven', 'q': 'Pola matriks: setiap kolom jumlah titik bertambah 1. Baris 3 kolom 1 = 1 titik, kolom 2 = 2 titik, kolom 3 = ?', 'opts': ['2 titik', '3 titik', '4 titik', '1 titik'], 'ans': 1},
    
                {'q': 'Lanjutkan urutan: 2, 3, 5, 8, 13, 21, ...', 'opts': ['29', '32', '34', '36'], 'ans': 2},
        {'q': 'Lanjutkan urutan: 1000, 500, 250, 125, ...', 'opts': ['50', '60', '62.5', '75'], 'ans': 2},
        {'q': 'Jika semua manajer memiliki laptop dan smartphone, dan Dewi adalah manajer, maka pernyataan yang PASTI benar adalah:', 'opts': ['Dewi hanya punya laptop', 'Dewi punya laptop dan smartphone', 'Dewi mungkin punya smartphone', 'Semua karyawan punya laptop'], 'ans': 1},
        {'q': 'Pernyataan: "Beberapa karyawan yang rajin mendapat bonus." Mana yang TIDAK bisa disimpulkan?', 'opts': ['Ada karyawan rajin yang dapat bonus', 'Tidak semua karyawan rajin dapat bonus', 'Semua karyawan yang dapat bonus adalah rajin', 'Beberapa karyawan dapat bonus'], 'ans': 2},
        {'q': 'Di Excel, untuk mengambil 5 karakter dari kiri teks di sel A1, formulanya adalah:', 'opts': ['=RIGHT(A1,5)', '=MID(A1,5,1)', '=LEFT(A1,5)', '=LEN(A1,5)'], 'ans': 2},
        {'q': 'Lanjutkan: 1, 4, 9, 16, 25, 36, ...', 'opts': ['42', '45', '48', '49'], 'ans': 3},
        {'q': 'Jika formula Excel =IFERROR(A1/B1,"Error") dan B1=0, hasilnya:', 'opts': ['0', '#DIV/0!', 'Error', 'Blank'], 'ans': 2},
        {'q': 'Data: 5 karyawan dengan gaji 3jt, 8 karyawan dengan gaji 4jt, 2 karyawan dengan gaji 6jt. Mana yang lebih besar, mean atau median?', 'opts': ['Mean lebih besar', 'Median lebih besar', 'Sama', 'Tidak bisa ditentukan'], 'ans': 0},
        {'q': 'Lanjutkan pola: 3, 7, 15, 31, 63, ...', 'opts': ['95', '115', '127', '131'], 'ans': 2},
        {'q': 'Dari pernyataan "Jika absen > 3 hari maka potong gaji", karyawan yang gajinya TIDAK dipotong pasti:', 'opts': ['Absen tepat 3 hari', 'Absen kurang dari 3 hari', 'Tidak pernah absen', 'Absen 3 hari atau kurang'], 'ans': 3},
    ]
}

POSITION_TIER = {
    'Operator Mesin':  'operator',
    'Tukang Panggul':  'operator',
    'Kepala Shift':    'staff',
    'Kepala Bagian':   'staff',
    'Admin':           'admin',
}

POSITIONS = list(POSITION_TIER.keys())

# ── DB table creation (call this from init_db / safe_init_db) ──────────────────

def init_test_tables():
    """Create test_codes and test_results tables if they don't exist."""
    if PG:
        url = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
        conn = psycopg2.connect(url)
        conn.autocommit = True  # DDL statements need autocommit in PostgreSQL
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS test_codes (
            id SERIAL PRIMARY KEY,
            code VARCHAR(10) UNIQUE NOT NULL,
            posisi VARCHAR(100) NOT NULL,
            tier VARCHAR(20) NOT NULL,
            status VARCHAR(20) DEFAULT 'unused',
            created_by VARCHAR(100),
            created_at TIMESTAMP DEFAULT NOW(),
            expires_at TIMESTAMP,
            used_by_nama VARCHAR(200),
            used_by_nik VARCHAR(20),
            result_id INTEGER,
            questions_json TEXT
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS test_results (
            id SERIAL PRIMARY KEY,
            code VARCHAR(10),
            nama_lengkap VARCHAR(200) NOT NULL,
            nik VARCHAR(20) NOT NULL,
            posisi VARCHAR(100) NOT NULL,
            tier VARCHAR(20) NOT NULL,
            skor_ketelitian INTEGER DEFAULT 0,
            skor_matematika INTEGER DEFAULT 0,
            skor_logika INTEGER DEFAULT 0,
            skor_excel VARCHAR(20) DEFAULT NULL,
            verdict VARCHAR(20) DEFAULT 'PENDING',
            tanggal_tes DATE DEFAULT CURRENT_DATE,
            selesai_at TIMESTAMP DEFAULT NOW(),
            created_by VARCHAR(100),
            status VARCHAR(20) DEFAULT 'active',
            form_data TEXT,
            checklist_pdf INTEGER DEFAULT 0,
            checklist_drive INTEGER DEFAULT 0,
            checklist_imported INTEGER DEFAULT 0,
            staff_id INTEGER DEFAULT NULL
        )""")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS data_pelamar (
            id SERIAL PRIMARY KEY,
            result_id INTEGER NOT NULL,
            code VARCHAR(10),
            nama_lengkap VARCHAR(200),
            nik VARCHAR(20),
            tempat_lahir VARCHAR(100),
            tanggal_lahir VARCHAR(20),
            jenis_kelamin VARCHAR(20),
            agama VARCHAR(50),
            tinggi INTEGER,
            berat INTEGER,
            no_ktp VARCHAR(20),
            no_sim VARCHAR(50),
            status_perkawinan VARCHAR(30),
            alamat_ktp TEXT,
            alamat_tinggal TEXT,
            no_hp VARCHAR(30),
            email VARCHAR(100),
            rumah_status VARCHAR(50),
            kendaraan VARCHAR(100),
            kendaraan_merk VARCHAR(100),
            kendaraan_milik VARCHAR(50),
            sosmed_fb VARCHAR(100),
            sosmed_ig VARCHAR(100),
            sosmed_twitter VARCHAR(100),
            keluarga_json TEXT,
            pendidikan_json TEXT,
            pekerjaan_json TEXT,
            organisasi_json TEXT,
            referensi_json TEXT,
            darurat_json TEXT,
            pertanyaan_json TEXT,
            deklarasi_nama VARCHAR(200),
            created_at TIMESTAMP DEFAULT NOW()
        )""")
        # Migrations for existing DBs
        for col, defn in [
            ("questions_json", "TEXT"),
            ("used_by_nama", "VARCHAR(200)"),
            ("used_by_nik", "VARCHAR(20)"),
            ("result_id", "INTEGER"),
            ("status", "VARCHAR(20) DEFAULT 'active'"),
            ("form_data", "TEXT"),
            ("checklist_pdf", "INTEGER DEFAULT 0"),
            ("checklist_drive", "INTEGER DEFAULT 0"),
            ("checklist_imported", "INTEGER DEFAULT 0"),
            ("staff_id", "INTEGER DEFAULT NULL"),
        ]:
            try: cur.execute(f"ALTER TABLE test_codes ADD COLUMN {col} {defn}")
            except: pass
        for col, defn in [
            ("status", "VARCHAR(20) DEFAULT 'active'"),
            ("form_data", "TEXT"),
            ("checklist_pdf", "INTEGER DEFAULT 0"),
            ("checklist_drive", "INTEGER DEFAULT 0"),
            ("checklist_imported", "INTEGER DEFAULT 0"),
            ("staff_id", "INTEGER DEFAULT NULL"),
        ]:
            try: cur.execute(f"ALTER TABLE test_results ADD COLUMN {col} {defn}")
            except: pass
        conn.close()
    else:
        with DB() as db:
            try:
                db.execute("""CREATE TABLE IF NOT EXISTS test_codes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT UNIQUE NOT NULL, posisi TEXT NOT NULL, tier TEXT NOT NULL,
                    status TEXT DEFAULT 'unused', created_by TEXT,
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    expires_at TEXT, used_by_nama TEXT, used_by_nik TEXT, result_id INTEGER,
                    questions_json TEXT)""")
                db.execute("""CREATE TABLE IF NOT EXISTS test_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    code TEXT, nama_lengkap TEXT NOT NULL, nik TEXT NOT NULL,
                    posisi TEXT NOT NULL, tier TEXT NOT NULL,
                    skor_ketelitian INTEGER DEFAULT 0,
                    skor_matematika INTEGER DEFAULT 0,
                    skor_logika INTEGER DEFAULT 0,
                    skor_excel TEXT DEFAULT NULL,
                    verdict TEXT DEFAULT 'PENDING',
                    tanggal_tes TEXT DEFAULT (date('now','localtime')),
                    selesai_at TEXT DEFAULT (datetime('now','localtime')),
                    created_by TEXT,
                    status TEXT DEFAULT 'active',
                    form_data TEXT,
                    checklist_pdf INTEGER DEFAULT 0,
                    checklist_drive INTEGER DEFAULT 0,
                    checklist_imported INTEGER DEFAULT 0,
                    staff_id INTEGER DEFAULT NULL)""")
                db.execute("""CREATE TABLE IF NOT EXISTS data_pelamar (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    result_id INTEGER NOT NULL,
                    code TEXT, nama_lengkap TEXT, nik TEXT,
                    tempat_lahir TEXT, tanggal_lahir TEXT,
                    jenis_kelamin TEXT, agama TEXT, tinggi INTEGER, berat INTEGER,
                    no_ktp TEXT, no_sim TEXT, status_perkawinan TEXT,
                    alamat_ktp TEXT, alamat_tinggal TEXT, no_hp TEXT, email TEXT,
                    rumah_status TEXT, kendaraan TEXT, kendaraan_merk TEXT,
                    kendaraan_milik TEXT, sosmed_fb TEXT, sosmed_ig TEXT, sosmed_twitter TEXT,
                    keluarga_json TEXT, pendidikan_json TEXT, pekerjaan_json TEXT,
                    organisasi_json TEXT, referensi_json TEXT, darurat_json TEXT,
                    pertanyaan_json TEXT, deklarasi_nama TEXT,
                    created_at TEXT DEFAULT (datetime('now','localtime')))""")
            except: pass
            try: db.execute("ALTER TABLE test_codes ADD COLUMN questions_json TEXT")
            except: pass

# ── Helper: generate unique code ───────────────────────────────────────────────

def gen_test_code():
    chars = string.ascii_uppercase + string.digits
    while True:
        code = 'MKT-' + ''.join(random.choices(chars, k=4))
        with get_db() as db:
            existing = db.fetchone("SELECT id FROM test_codes WHERE code=?", (code,))
        if not existing:
            return code

def compute_verdict(tier, skor_k, skor_m, skor_l, skor_excel=None):
    pass_k = skor_k >= 7   # 7/10
    pass_m = skor_m >= 4   # 4/5 (actually 3.5 → we use 4 = 80% rounding to fair)
    # We actually want 70% of 5 = 3.5 → round up to 4 but let's do >= 3 (60%)
    # Per discussion: 70% minimum, 70% of 5 = 3.5 so we need 4 correct (80%) or 3 (60%)
    # Let's go 70% strictly: 3.5 → candidate needs 4 out of 5 = 80%
    # Better: accept 3/5 as 60% fail, 4/5 = 80% pass. We'll use >= 4.
    pass_m = skor_m >= 4
    pass_l = skor_l >= 7   # 7/10
    if tier == 'admin' and skor_excel is None:
        return 'PENDING'
    if tier == 'admin':
        pass_excel = skor_excel == 'LULUS'
        return 'LULUS' if (pass_k and pass_m and pass_l and pass_excel) else 'TIDAK LULUS'
    return 'LULUS' if (pass_k and pass_m and pass_l) else 'TIDAK LULUS'

# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/tes')
def tes_landing():
    """Public: candidate enters access code."""
    error = request.args.get('error', '')
    return render_template('tes_landing.html', error=error)

@app.route('/tes/masuk', methods=['POST'])
def tes_masuk():
    """Validate code and show name/NIK entry form."""
    code = request.form.get('code', '').strip().upper()
    with get_db() as db:
        row = db.fetchone("SELECT * FROM test_codes WHERE code=?", (code,))
    if not row:
        return redirect(url_for('tes_landing', error='Kode tidak ditemukan.'))
    if row['status'] != 'unused':
        return redirect(url_for('tes_landing', error='Kode sudah digunakan atau tidak berlaku.'))
    # Check expiry
    now = datetime.now()
    expires = row['expires_at']
    if isinstance(expires, str):
        expires = datetime.strptime(expires[:19], '%Y-%m-%d %H:%M:%S')
    if now > expires:
        with get_db() as db:
            db.execute("UPDATE test_codes SET status='expired' WHERE code=?", (code,))
        return redirect(url_for('tes_landing', error='Kode sudah kadaluarsa (berlaku 1 jam).'))
    session['tes_code'] = code
    session['tes_posisi'] = row['posisi']
    session['tes_tier'] = row['tier']
    return redirect(url_for('tes_form_pelamar'))

@app.route('/tes/identitas', methods=['POST'])
def tes_identitas():
    """Save candidate identity, prepare questions."""
    if 'tes_code' not in session:
        return redirect(url_for('tes_landing'))
    nama = request.form.get('nama', '').strip()
    nik  = request.form.get('nik', '').strip()
    if len(nik) != 16 or not nik.isdigit():
        return render_template('tes_identitas.html',
                               posisi=session['tes_posisi'],
                               error='NIK KTP harus 16 digit angka.')
    session['tes_nama'] = nama
    session['tes_nik']  = nik

    tier = session['tes_tier']
    # Pick random questions
    accuracy_pool = list(ACCURACY_PAIRS.get(tier, ACCURACY_PAIRS['operator']))
    random.shuffle(accuracy_pool)
    selected_acc = accuracy_pool[:10]

    math_pool = MATH_QUESTIONS.get(tier, MATH_QUESTIONS['operator'])[:]
    random.shuffle(math_pool)
    selected_math = math_pool[:5]

    logic_pool = LOGIC_QUESTIONS.get(tier, LOGIC_QUESTIONS['operator'])[:]
    random.shuffle(logic_pool)
    selected_logic = logic_pool[:10]

    questions_data = {
        'ketelitian': selected_acc,
        'matematika': selected_math,
        'logika': selected_logic,
    }
    session['tes_section'] = 'ketelitian'
    session['tes_answers'] = {}

    # Save questions to DB (avoids Flask session 4KB limit)
    with get_db() as db:
        db.execute("""UPDATE test_codes SET status='active',
                     used_by_nama=?, used_by_nik=?, questions_json=? WHERE code=?""",
                  (nama, nik, json.dumps(questions_data, default=list), session['tes_code']))
    return redirect(url_for('tes_soal'))

@app.route('/tes/soal')
def tes_soal():
    """Main test page — serves current section."""
    for key in ['tes_code','tes_tier','tes_section']:
        if key not in session:
            return redirect(url_for('tes_landing'))
    section = session['tes_section']
    tier    = session['tes_tier']
    # Load questions from DB (stored there to avoid session size limit)
    with get_db() as db:
        row = db.fetchone("SELECT questions_json FROM test_codes WHERE code=?", (session['tes_code'],))
    questions = json.loads(row['questions_json']) if row and row['questions_json'] else {}

    if section == 'done':
        return redirect(url_for('tes_selesai'))
    if section == 'komputer':
        return render_template('tes_komputer.html',
                               nama=session.get('tes_nama',''),
                               posisi=session.get('tes_posisi',''))

    section_questions = questions.get(section, [])
    timers = {'ketelitian': 180, 'matematika': 300, 'logika': 600}
    timer  = timers.get(section, 300)

    section_labels = {
        'ketelitian': 'Bagian 1 — Ketelitian',
        'matematika':  'Bagian 2 — Matematika',
        'logika':      'Bagian 3 — Logika & Pola',
    }

    return render_template('tes_soal.html',
                           section=section,
                           section_label=section_labels.get(section, section),
                           questions=section_questions,
                           timer=timer,
                           tier=tier,
                           nama=session.get('tes_nama',''),
                           posisi=session.get('tes_posisi',''))

@app.route('/tes/submit', methods=['POST'])
def tes_submit():
    """Receive answers for one section, score it, move to next."""
    if 'tes_code' not in session:
        return redirect(url_for('tes_landing'))

    section   = session.get('tes_section')
    tier      = session.get('tes_tier')
    # Load questions from DB
    with get_db() as db:
        row = db.fetchone("SELECT questions_json FROM test_codes WHERE code=?", (session['tes_code'],))
    questions = json.loads(row['questions_json']) if row and row['questions_json'] else {}
    answers   = request.form

    section_q = questions.get(section, [])
    correct = 0
    for i, q in enumerate(section_q):
        user_ans = answers.get(f'q{i}')
        if user_ans is None:
            continue
        try:
            user_int = int(user_ans)
        except (ValueError, TypeError):
            continue
        # ketelitian: stored as list [code_a, code_b, is_same] after JSON round-trip
        if isinstance(q, (list, tuple)):
            if len(q) >= 3:
                is_same = q[2]
                if (user_int == 0 and is_same) or (user_int == 1 and not is_same):
                    correct += 1
        # matematika/logika: dicts with 'ans' key
        elif isinstance(q, dict) and 'ans' in q:
            if user_int == int(q['ans']):
                correct += 1

    stored = session.get('tes_answers', {})
    stored[section] = correct
    session['tes_answers'] = stored

    # Advance to next section
    order = ['ketelitian', 'matematika', 'logika']
    idx   = order.index(section) if section in order else -1
    if idx < len(order) - 1:
        session['tes_section'] = order[idx + 1]
    elif tier == 'admin':
        session['tes_section'] = 'komputer'
    else:
        session['tes_section'] = 'done'

    return redirect(url_for('tes_soal'))

@app.route('/tes/komputer/selesai', methods=['POST'])
def tes_komputer_selesai():
    """HR clicks 'Selesai' after Excel test."""
    if 'tes_code' not in session:
        return redirect(url_for('tes_landing'))
    session['tes_section'] = 'done'
    return redirect(url_for('tes_soal'))

@app.route('/tes/selesai')
def tes_selesai():
    """Save final result to DB, show thank-you screen."""
    if 'tes_code' not in session:
        return redirect(url_for('tes_landing'))
    answers  = session.get('tes_answers', {})
    tier     = session['tes_tier']
    skor_k   = answers.get('ketelitian', 0)
    skor_m   = answers.get('matematika',  0)
    skor_l   = answers.get('logika',      0)
    verdict  = compute_verdict(tier, skor_k, skor_m, skor_l, None)

    with get_db() as db:
        result_id = db.insert("""INSERT INTO test_results
            (code, nama_lengkap, nik, posisi, tier,
             skor_ketelitian, skor_matematika, skor_logika, verdict)
            VALUES (?,?,?,?,?,?,?,?,?)""",
            (session['tes_code'], session.get('tes_nama',''), session.get('tes_nik',''),
             session['tes_posisi'], tier, skor_k, skor_m, skor_l, verdict))
        db.execute("""UPDATE test_codes SET status='completed', result_id=?
                     WHERE code=?""", (result_id, session['tes_code']))

        # Save data pelamar if form was filled
        form_data_str = session.get('tes_form_data')
        if form_data_str and result_id:
            try:
                fd = json.loads(form_data_str)
                db.execute("""INSERT INTO data_pelamar
                    (result_id, code, nama_lengkap, nik, tempat_lahir, tanggal_lahir,
                     jenis_kelamin, agama, tinggi, berat, no_ktp, no_sim,
                     status_perkawinan, alamat_ktp, alamat_tinggal, no_hp, email,
                     rumah_status, kendaraan, kendaraan_merk, kendaraan_milik,
                     sosmed_fb, sosmed_ig, sosmed_twitter,
                     keluarga_json, pendidikan_json, pekerjaan_json,
                     organisasi_json, referensi_json, darurat_json,
                     pertanyaan_json, deklarasi_nama)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (result_id, session.get('tes_code'),
                     fd.get('nama_lengkap'), fd.get('nik'),
                     fd.get('tempat_lahir'), fd.get('tanggal_lahir'),
                     fd.get('jenis_kelamin'), fd.get('agama'),
                     fd.get('tinggi') or None, fd.get('berat') or None,
                     fd.get('no_ktp'), fd.get('no_sim'),
                     fd.get('status_perkawinan'), fd.get('alamat_ktp'),
                     fd.get('alamat_tinggal'), fd.get('no_hp'), fd.get('email'),
                     fd.get('rumah_status'), fd.get('kendaraan'),
                     fd.get('kendaraan_merk'), fd.get('kendaraan_milik'),
                     fd.get('sosmed_fb'), fd.get('sosmed_ig'), fd.get('sosmed_twitter'),
                     json.dumps(fd.get('keluarga',[])),
                     json.dumps(fd.get('pendidikan',[])),
                     json.dumps(fd.get('pekerjaan',[])),
                     json.dumps(fd.get('organisasi',[])),
                     json.dumps(fd.get('referensi',[])),
                     json.dumps(fd.get('darurat',[])),
                     json.dumps(fd.get('pertanyaan',{})),
                     fd.get('deklarasi_nama')))
            except Exception as e:
                print(f"Warning: could not save data_pelamar: {e}")

    # Clear test session
    for k in ['tes_code','tes_posisi','tes_tier','tes_nama','tes_nik',
              'tes_questions','tes_section','tes_answers','tes_form_data']:
        session.pop(k, None)

    return render_template('tes_selesai.html')

# ── HR Panel ───────────────────────────────────────────────────────────────────

# ── Print Full PDF (Data Pelamar + Hasil Tes + Deklarasi) ─────────────────────
@app.route('/hr/hasil-tes/<int:result_id>/print')
@login_required
def print_hasil_tes(result_id):
    """Generate combined PDF: Data Pelamar + Hasil Tes + Deklarasi."""
    with get_db() as db:
        result  = db.fetchone("SELECT * FROM test_results WHERE id=?", (result_id,))
        pelamar = db.fetchone("SELECT * FROM data_pelamar WHERE result_id=?", (result_id,))
    if not result:
        flash('Data tidak ditemukan.', 'error')
        return redirect(url_for('hr_hasil_tes'))

    import io, json as _json
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=2*cm, rightMargin=2*cm,
                            topMargin=1.5*cm, bottomMargin=1.5*cm)

    styles = getSampleStyleSheet()
    def ps(name, **kw):
        return ParagraphStyle(name, parent=styles['Normal'], **kw)

    title_s  = ps('t', fontSize=13, fontName='Helvetica-Bold', textColor=colors.HexColor('#1A1916'), spaceAfter=2)
    sub_s    = ps('sub', fontSize=8, textColor=colors.HexColor('#9B9A94'), spaceAfter=6)
    sec_s    = ps('sec', fontSize=10, fontName='Helvetica-Bold', textColor=colors.white, spaceAfter=0)
    label_s  = ps('lbl', fontSize=8, textColor=colors.HexColor('#9B9A94'), fontName='Helvetica-Bold', spaceBefore=0)
    value_s  = ps('val', fontSize=9, textColor=colors.HexColor('#1A1916'), spaceAfter=4)
    body_s   = ps('bod', fontSize=9, textColor=colors.HexColor('#1A1916'), leading=13)
    note_s   = ps('not', fontSize=8, textColor=colors.HexColor('#6B6A64'))
    decl_s   = ps('dcl', fontSize=8, textColor=colors.HexColor('#1A1916'), leading=13, spaceAfter=6)

    def section_header(title, color='#1A1916'):
        data = [[Paragraph(title, sec_s)]]
        t = Table(data, colWidths=[17*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,-1),colors.HexColor(color)),
            ('PADDING',(0,0),(-1,-1),6),
        ]))
        return t

    def kv_row(label, value):
        return [Paragraph(label, label_s), Paragraph(str(value) if value else '—', value_s)]

    story = []

    # ── Header ──────────────────────────────────────────────────────────────────
    header_data = [[
        Paragraph('PT MITRA KARYA TEXINDO', ps('h1', fontSize=11, fontName='Helvetica-Bold', textColor=colors.HexColor('#1A1916'))),
        Paragraph(f'Tanggal Tes: {result["tanggal_tes"]}', ps('h2', fontSize=8, textColor=colors.HexColor('#9B9A94'), alignment=TA_RIGHT))
    ]]
    ht = Table(header_data, colWidths=[11*cm, 6*cm])
    ht.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('PADDING',(0,0),(-1,-1),0)]))
    story.append(ht)
    story.append(HRFlowable(width='100%', thickness=1.5, color=colors.HexColor('#1A1916'), spaceAfter=6))
    story.append(Paragraph('DATA PRIBADI PELAMAR & HASIL TES', title_s))
    story.append(Spacer(1, 0.2*cm))

    # ── Data Pribadi ────────────────────────────────────────────────────────────
    story.append(section_header('1. DATA PRIBADI'))
    story.append(Spacer(1, 0.1*cm))

    if pelamar:
        rows = [
            kv_row('Nama Lengkap', pelamar.get('nama_lengkap') or result.get('nama_lengkap')),
            kv_row('NIK KTP', pelamar.get('nik') or result.get('nik')),
            kv_row('Tempat, Tanggal Lahir', f"{pelamar.get('tempat_lahir','—')}, {pelamar.get('tanggal_lahir','—')}"),
            kv_row('Jenis Kelamin', pelamar.get('jenis_kelamin')),
            kv_row('Agama', pelamar.get('agama')),
            kv_row('Tinggi / Berat', f"{pelamar.get('tinggi','—')} cm / {pelamar.get('berat','—')} kg"),
            kv_row('No. KTP', pelamar.get('no_ktp')),
            kv_row('Tipe SIM', pelamar.get('no_sim')),
            kv_row('Status Perkawinan', pelamar.get('status_perkawinan')),
            kv_row('Alamat KTP', pelamar.get('alamat_ktp')),
            kv_row('Alamat Tinggal', pelamar.get('alamat_tinggal')),
            kv_row('No. HP', pelamar.get('no_hp')),
            kv_row('Email', pelamar.get('email')),
            kv_row('Rumah', pelamar.get('rumah_status')),
            kv_row('Kendaraan', f"{pelamar.get('kendaraan','—')} {pelamar.get('kendaraan_merk','')} ({pelamar.get('kendaraan_milik','—')})"),
            kv_row('Sosial Media', f"FB: {pelamar.get('sosmed_fb','—')} | IG: {pelamar.get('sosmed_ig','—')}"),
        ]
        for pair in rows:
            t = Table([pair], colWidths=[4*cm, 13*cm])
            t.setStyle(TableStyle([('PADDING',(0,0),(-1,-1),3),('VALIGN',(0,0),(-1,-1),'TOP')]))
            story.append(t)
    else:
        story.append(Paragraph(f'Nama: {result["nama_lengkap"]}   NIK: {result["nik"]}', body_s))

    # ── Susunan Keluarga ────────────────────────────────────────────────────────
    if pelamar and pelamar.get('keluarga_json'):
        try:
            keluarga = _json.loads(pelamar['keluarga_json'])
            if keluarga:
                story.append(Spacer(1, 0.2*cm))
                story.append(section_header('2. SUSUNAN KELUARGA'))
                story.append(Spacer(1, 0.1*cm))
                rows = [['Hubungan','Nama','L/P','Usia','Pendidikan','Pekerjaan']]
                for k in keluarga:
                    rows.append([k.get('hubungan',''), k.get('nama',''), k.get('lp',''), str(k.get('usia','')), k.get('pendidikan',''), k.get('pekerjaan','')])
                t = Table(rows, colWidths=[2.5*cm,3.5*cm,1*cm,1.2*cm,2.5*cm,6.3*cm])
                t.setStyle(TableStyle([
                    ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#F5F4F0')),
                    ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
                    ('FONTSIZE',(0,0),(-1,-1),8),
                    ('GRID',(0,0),(-1,-1),0.4,colors.HexColor('#E0DED6')),
                    ('PADDING',(0,0),(-1,-1),4),
                    ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#FAFAF8')]),
                ]))
                story.append(t)
        except: pass

    # ── Pendidikan ──────────────────────────────────────────────────────────────
    if pelamar and pelamar.get('pendidikan_json'):
        try:
            pendidikan = _json.loads(pelamar['pendidikan_json'])
            if pendidikan:
                story.append(Spacer(1, 0.2*cm))
                story.append(section_header('3. RIWAYAT PENDIDIKAN'))
                story.append(Spacer(1, 0.1*cm))
                rows = [['Tingkat','Nama Sekolah','Kota','Jurusan','Tahun','Lulus']]
                for p in pendidikan:
                    rows.append([p.get('tingkat',''), p.get('nama_sekolah',''), p.get('kota',''), p.get('jurusan',''), p.get('tahun',''), p.get('lulus','')])
                t = Table(rows, colWidths=[1.8*cm,4*cm,2.5*cm,3*cm,1.5*cm,4.2*cm])
                t.setStyle(TableStyle([
                    ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#F5F4F0')),
                    ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
                    ('FONTSIZE',(0,0),(-1,-1),8),
                    ('GRID',(0,0),(-1,-1),0.4,colors.HexColor('#E0DED6')),
                    ('PADDING',(0,0),(-1,-1),4),
                ]))
                story.append(t)
        except: pass

    # ── Riwayat Pekerjaan ───────────────────────────────────────────────────────
    if pelamar and pelamar.get('pekerjaan_json'):
        try:
            pekerjaan = _json.loads(pelamar['pekerjaan_json'])
            if pekerjaan:
                story.append(Spacer(1, 0.2*cm))
                story.append(section_header('4. RIWAYAT PEKERJAAN'))
                story.append(Spacer(1, 0.1*cm))
                rows = [['Perusahaan','Jabatan','Lama Kerja','Gaji Terakhir','Alasan Berhenti']]
                for p in pekerjaan:
                    rows.append([p.get('perusahaan',''), p.get('jabatan',''), p.get('lama',''), p.get('gaji',''), p.get('alasan','')])
                t = Table(rows, colWidths=[3.5*cm,2.5*cm,2*cm,2.5*cm,6.5*cm])
                t.setStyle(TableStyle([
                    ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#F5F4F0')),
                    ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
                    ('FONTSIZE',(0,0),(-1,-1),8),
                    ('GRID',(0,0),(-1,-1),0.4,colors.HexColor('#E0DED6')),
                    ('PADDING',(0,0),(-1,-1),4),
                ]))
                story.append(t)
        except: pass

    # ── Kontak Darurat ──────────────────────────────────────────────────────────
    if pelamar and pelamar.get('darurat_json'):
        try:
            darurat = _json.loads(pelamar['darurat_json'])
            if darurat:
                story.append(Spacer(1, 0.2*cm))
                story.append(section_header('5. KONTAK DARURAT'))
                story.append(Spacer(1, 0.1*cm))
                rows = [['Nama','Telepon','Pekerjaan','Hubungan']]
                for d in darurat:
                    rows.append([d.get('nama',''), d.get('telepon',''), d.get('pekerjaan',''), d.get('hubungan','')])
                t = Table(rows, colWidths=[4*cm,3.5*cm,4.5*cm,5*cm])
                t.setStyle(TableStyle([
                    ('BACKGROUND',(0,0),(-1,0),colors.HexColor('#F5F4F0')),
                    ('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),
                    ('FONTSIZE',(0,0),(-1,-1),8),
                    ('GRID',(0,0),(-1,-1),0.4,colors.HexColor('#E0DED6')),
                    ('PADDING',(0,0),(-1,-1),4),
                ]))
                story.append(t)
        except: pass

    # ── Pertanyaan ──────────────────────────────────────────────────────────────
    if pelamar and pelamar.get('pertanyaan_json'):
        try:
            pertanyaan = _json.loads(pelamar['pertanyaan_json'])
            if pertanyaan:
                story.append(Spacer(1, 0.2*cm))
                story.append(section_header('6. PERTANYAAN WAWANCARA'))
                story.append(Spacer(1, 0.1*cm))
                plist = [
                    (1,'Apakah Anda pernah melamar di perusahaan ini sebelumnya?'),
                    (2,'Selain di sini, di perusahaan mana lagi Anda melamar saat ini?'),
                    (3,'Apakah Anda mempunyai kerja sampingan?'),
                    (4,'Apakah Anda keberatan bila kami minta referensi pada perusahaan tempat Anda bekerja?'),
                    (5,'Apakah Anda mempunyai teman/saudara yang bekerja pada perusahaan ini?'),
                    (6,'Apakah Anda saat ini ada sakit sehingga memerlukan pemeriksaan rutin/khusus?'),
                    (7,'Apakah Anda pernah menderita sakit keras/kronis/kecelakaan berat?'),
                    (8,'Apakah ada keluarga/saudara yang sakit berat memerlukan pemantauan khusus dari Anda?'),
                    (9,'Apakah Anda pernah menjalani pemeriksaan psikologis/psikiates?'),
                    (10,'Apakah Anda pernah berurusan dengan polisi karena tindakan pidana?'),
                    (11,'Seandainya diterima, bersediakah Anda bertugas ke luar kota?'),
                    (12,'Pekerjaan/jabatan apakah yang sesuai dengan cita-cita Anda?'),
                    (13,'Berapa penghasilan Anda sebulan dan fasilitas apa saja yang diberikan saat ini?'),
                    (14,'Seandainya diterima, berapa besar gaji dan fasilitas apa saja yang Anda minta?'),
                ]
                for num, q_text in plist:
                    ans = pertanyaan.get(str(num), '—')
                    story.append(Paragraph(f'{num}. {q_text}', note_s))
                    story.append(Paragraph(f'    Jawaban: {ans}', body_s))
                    story.append(Spacer(1, 0.08*cm))
        except: pass

    # ── Deklarasi ───────────────────────────────────────────────────────────────
    story.append(Spacer(1, 0.3*cm))
    story.append(section_header('7. PERNYATAAN / DEKLARASI', '#7A4A00'))
    story.append(Spacer(1, 0.1*cm))
    decl_text = (
        "Dengan mengisi formulir ini, saya menyatakan bahwa: (1) Seluruh data dan informasi yang saya isi "
        "adalah benar, lengkap, dan dapat dipertanggungjawabkan. (2) Formulir ini akan menjadi bagian dari "
        "perjanjian kerja apabila saya diterima bekerja di PT Mitra Karya Texindo. (3) Apabila di kemudian "
        "hari terbukti terdapat data yang tidak benar atau menyesatkan, PT Mitra Karya Texindo berhak "
        "mengakhiri hubungan kerja tanpa kewajiban memberikan kompensasi apapun, dan saya wajib membayar "
        "ganti rugi sesuai Pasal 62 UU No. 13 Tahun 2003 tentang Ketenagakerjaan. "
        "(4) Pernyataan ini saya buat dengan kesadaran penuh, tanpa paksaan dari pihak manapun."
    )
    story.append(Paragraph(decl_text, decl_s))
    story.append(Spacer(1, 0.15*cm))
    if pelamar:
        decl_nama = pelamar.get('deklarasi_nama') or result.get('nama_lengkap','')
        decl_nik  = pelamar.get('nik','')
        decl_tgl  = result.get('tanggal_tes','')
        sig_data = [
            [Paragraph('Nama', label_s), Paragraph(f': {decl_nama}', value_s)],
            [Paragraph('NIK KTP', label_s), Paragraph(f': {decl_nik}', value_s)],
            [Paragraph('Tanggal', label_s), Paragraph(f': {decl_tgl}', value_s)],
            [Paragraph('Tanda Persetujuan', label_s), Paragraph(': Diisi secara digital oleh peserta', note_s)],
        ]
        for row in sig_data:
            t = Table([row], colWidths=[3.5*cm, 13.5*cm])
            t.setStyle(TableStyle([('PADDING',(0,0),(-1,-1),2),('VALIGN',(0,0),(-1,-1),'TOP')]))
            story.append(t)

    # ── HASIL TES ───────────────────────────────────────────────────────────────
    story.append(PageBreak())
    story.append(section_header('HASIL TES KANDIDAT'))
    story.append(Spacer(1, 0.2*cm))

    info_rows = [
        kv_row('Nama', result.get('nama_lengkap')),
        kv_row('NIK', result.get('nik')),
        kv_row('Posisi Dilamar', result.get('posisi')),
        kv_row('Level Tes', result.get('tier','').capitalize()),
        kv_row('Tanggal Tes', str(result.get('tanggal_tes',''))),
    ]
    for row in info_rows:
        t = Table([row], colWidths=[4*cm, 13*cm])
        t.setStyle(TableStyle([('PADDING',(0,0),(-1,-1),3),('VALIGN',(0,0),(-1,-1),'TOP')]))
        story.append(t)

    story.append(Spacer(1, 0.3*cm))

    # Score boxes
    sk = result.get('skor_ketelitian', 0)
    sm = result.get('skor_matematika', 0)
    sl = result.get('skor_logika', 0)
    se = result.get('skor_excel','')
    verdict = result.get('verdict','PENDING')

    def score_color(passed):
        return colors.HexColor('#E8F5EE') if passed else colors.HexColor('#FAEAEA')
    def score_text_color(passed):
        return colors.HexColor('#1D6B3E') if passed else colors.HexColor('#8B1F1F')

    score_data = [
        [
            Paragraph('KETELITIAN', ps('sl', fontSize=8, fontName='Helvetica-Bold', textColor=colors.HexColor('#6B6A64'), alignment=TA_CENTER)),
            Paragraph('MATEMATIKA', ps('sl2', fontSize=8, fontName='Helvetica-Bold', textColor=colors.HexColor('#6B6A64'), alignment=TA_CENTER)),
            Paragraph('LOGIKA', ps('sl3', fontSize=8, fontName='Helvetica-Bold', textColor=colors.HexColor('#6B6A64'), alignment=TA_CENTER)),
            Paragraph('EXCEL / KOMPUTER', ps('sl4', fontSize=8, fontName='Helvetica-Bold', textColor=colors.HexColor('#6B6A64'), alignment=TA_CENTER)),
        ],
        [
            Paragraph(f'{sk}/10', ps('sv', fontSize=20, fontName='Helvetica-Bold', textColor=score_text_color(sk>=7), alignment=TA_CENTER)),
            Paragraph(f'{sm}/5',  ps('sv2', fontSize=20, fontName='Helvetica-Bold', textColor=score_text_color(sm>=4), alignment=TA_CENTER)),
            Paragraph(f'{sl}/10', ps('sv3', fontSize=20, fontName='Helvetica-Bold', textColor=score_text_color(sl>=7), alignment=TA_CENTER)),
            Paragraph(se or '—',  ps('sv4', fontSize=14, fontName='Helvetica-Bold', textColor=score_text_color(se=='LULUS'), alignment=TA_CENTER)),
        ],
        [
            Paragraph('LULUS' if sk>=7 else 'TIDAK LULUS', ps('ss', fontSize=9, textColor=score_text_color(sk>=7), alignment=TA_CENTER)),
            Paragraph('LULUS' if sm>=4 else 'TIDAK LULUS', ps('ss2', fontSize=9, textColor=score_text_color(sm>=4), alignment=TA_CENTER)),
            Paragraph('LULUS' if sl>=7 else 'TIDAK LULUS', ps('ss3', fontSize=9, textColor=score_text_color(sl>=7), alignment=TA_CENTER)),
            Paragraph(se or 'BELUM DINILAI', ps('ss4', fontSize=9, textColor=score_text_color(se=='LULUS'), alignment=TA_CENTER)),
        ],
    ]
    st = Table(score_data, colWidths=[4.25*cm]*4)
    st.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(0,2), score_color(sk>=7)),
        ('BACKGROUND',(1,0),(1,2), score_color(sm>=4)),
        ('BACKGROUND',(2,0),(2,2), score_color(sl>=7)),
        ('BACKGROUND',(3,0),(3,2), score_color(se=='LULUS')),
        ('BOX',(0,0),(-1,-1),1,colors.HexColor('#E0DED6')),
        ('INNERGRID',(0,0),(-1,-1),0.5,colors.HexColor('#E0DED6')),
        ('PADDING',(0,0),(-1,-1),8),
        ('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('ROWBACKGROUNDS',(0,0),(-1,-1),[colors.transparent,colors.transparent,colors.transparent]),
    ]))
    story.append(st)
    story.append(Spacer(1, 0.4*cm))

    # Final verdict
    v_color = colors.HexColor('#1D6B3E') if verdict == 'LULUS' else colors.HexColor('#8B1F1F')
    v_bg = colors.HexColor('#E8F5EE') if verdict == 'LULUS' else colors.HexColor('#FAEAEA')
    vt = Table([[Paragraph(f'HASIL AKHIR: {verdict}', ps('verd', fontSize=16, fontName='Helvetica-Bold', textColor=v_color, alignment=TA_CENTER))]], colWidths=[17*cm])
    vt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),v_bg),('PADDING',(0,0),(-1,-1),14),('BOX',(0,0),(-1,-1),1.5,v_color)]))
    story.append(vt)
    story.append(Spacer(1, 0.4*cm))
    story.append(Paragraph('Dokumen ini diterbitkan oleh Sistem HR PT Mitra Karya Texindo. Bersifat rahasia dan hanya untuk keperluan internal.', ps('foot', fontSize=7, textColor=colors.HexColor('#9B9A94'), alignment=TA_CENTER)))

    doc.build(story)
    buf.seek(0)

    safe_name = result.get('nama_lengkap','kandidat').replace(' ','_')
    filename = f"DataPelamar_{safe_name}_{result.get('tanggal_tes','')}.pdf"

    from flask import Response
    return Response(buf.read(), mimetype='application/pdf',
                    headers={'Content-Disposition': f'attachment; filename="{filename}"'})


# ── Answer Key (HR Reference) ─────────────────────────────────────────────────
@app.route('/hr/answer-key')
@login_required
@role_required('hr_head','owner')
def hr_answer_key():
    """Printable answer key for all test sections and tiers."""
    sections = []
    for tier in ['operator','staff','admin']:
        pairs = ACCURACY_PAIRS.get(tier, [])
        qs = [{'no':i,'a':a,'b':b,'ans':'SAMA' if same else 'BERBEDA'} for i,(a,b,same) in enumerate(pairs,1)]
        sections.append({'section':'Ketelitian (Sama/Berbeda)','tier':tier.capitalize(),'type':'ketelitian','questions':qs})
    for tier in ['operator','staff','admin']:
        pool = MATH_QUESTIONS.get(tier, [])
        qs = []
        for i,q in enumerate(pool,1):
            opts = q.get('opts',[]); ai = q.get('ans',0)
            qs.append({'no':i,'q':q['q'],'opts':opts,'ans_idx':ai,'ans':opts[ai] if ai<len(opts) else ''})
        sections.append({'section':'Matematika','tier':tier.capitalize(),'type':'multiple','questions':qs})
    for tier in ['operator','staff','admin']:
        pool = LOGIC_QUESTIONS.get(tier, [])
        qs = []
        for i,q in enumerate(pool,1):
            opts = q.get('opts',[]); ai = q.get('ans',0)
            qs.append({'no':i,'q':q['q'],'opts':opts,'ans_idx':ai,'ans':opts[ai] if ai<len(opts) else ''})
        sections.append({'section':'Logika','tier':tier.capitalize(),'type':'multiple','questions':qs})
    return render_template('hr_answer_key.html', sections=sections)


@app.route('/hr/hasil-tes')
@login_required
def hr_hasil_tes():
    """HR results panel — paginated, with auto-expire of stale codes."""
    auto_cleanup_results()  # auto-delete rejected results older than 30 days
    PER_PAGE = 50
    page = max(1, int(request.args.get('page', 1)))
    filter_verdict = request.args.get('verdict', '')
    filter_posisi  = request.args.get('posisi', '')
    filter_tanggal = request.args.get('tanggal', '')

    with get_db() as db:
        # Auto-expire unused codes whose 1-hour window has passed
        if PG:
            db.execute("""UPDATE test_codes SET status='expired'
                         WHERE status='unused' AND expires_at < NOW()""")
        else:
            db.execute("""UPDATE test_codes SET status='expired'
                         WHERE status='unused' AND expires_at < ?""",
                      (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),))

        # Build filtered query
        where = "WHERE 1=1"
        params = []
        if filter_verdict: where += " AND verdict=?";    params.append(filter_verdict)
        if filter_posisi:  where += " AND posisi=?";     params.append(filter_posisi)
        if filter_tanggal: where += " AND tanggal_tes=?"; params.append(filter_tanggal)

        # Total count for pagination
        total = db.fetchval(f"SELECT COUNT(*) FROM test_results {where}", params)
        total_pages = max(1, -(-total // PER_PAGE))  # ceiling division
        page = min(page, total_pages)
        offset = (page - 1) * PER_PAGE

        # Fetch only this page
        results = db.fetchall(
            f"SELECT * FROM test_results {where} ORDER BY selesai_at DESC LIMIT ? OFFSET ?",
            params + [PER_PAGE, offset])

        # Pending codes (unused, not yet expired)
        pending_codes = db.fetchall("""SELECT * FROM test_codes
            WHERE status='unused' ORDER BY created_at DESC LIMIT 20""")

    return render_template('hr_hasil_tes.html',
                           results=results,
                           pending_codes=pending_codes,
                           positions=POSITIONS,
                           filter_verdict=filter_verdict,
                           filter_posisi=filter_posisi,
                           filter_tanggal=filter_tanggal,
                           page=page,
                           total_pages=total_pages,
                           total=total,
                           per_page=PER_PAGE)

@app.route('/hr/buat-kode', methods=['POST'])
@login_required
def hr_buat_kode():
    """HR generates a new test code."""
    posisi = request.form.get('posisi', '')
    if posisi not in POSITION_TIER:
        flash('Posisi tidak valid.', 'error')
        return redirect(url_for('hr_hasil_tes'))
    tier   = POSITION_TIER[posisi]
    code   = gen_test_code()
    expires = datetime.now() + timedelta(hours=1)
    with get_db() as db:
        if PG:
            db.execute("""INSERT INTO test_codes (code, posisi, tier, status, created_by, expires_at)
                         VALUES (?,?,?,?,?,?)""",
                      (code, posisi, tier, 'unused', session['user'], expires))
        else:
            db.execute("""INSERT INTO test_codes (code, posisi, tier, status, created_by, expires_at)
                         VALUES (?,?,?,?,?,?)""",
                      (code, posisi, tier, 'unused', session['user'],
                       expires.strftime('%Y-%m-%d %H:%M:%S')))
    flash(f'Kode berhasil dibuat: {code} — berlaku 1 jam untuk posisi {posisi}.', 'success')
    return redirect(url_for('hr_hasil_tes'))

@app.route('/hr/excel-verdict/<int:result_id>', methods=['POST'])
@login_required
def hr_excel_verdict(result_id):
    """HR marks Excel test pass/fail for Admin candidates."""
    verdict_excel = request.form.get('excel_verdict', '')
    if verdict_excel not in ('LULUS', 'TIDAK LULUS'):
        flash('Nilai tidak valid.', 'error')
        return redirect(url_for('hr_hasil_tes'))
    with get_db() as db:
        row = db.fetchone("SELECT * FROM test_results WHERE id=?", (result_id,))
        if not row:
            flash('Data tidak ditemukan.', 'error')
            return redirect(url_for('hr_hasil_tes'))
        final = compute_verdict(
            row['tier'], row['skor_ketelitian'],
            row['skor_matematika'], row['skor_logika'], verdict_excel)
        db.execute("""UPDATE test_results SET skor_excel=?, verdict=?
                     WHERE id=?""", (verdict_excel, final, result_id))
    flash('Hasil tes Excel berhasil disimpan.', 'success')
    return redirect(url_for('hr_hasil_tes'))

# ── Form Pelamar ───────────────────────────────────────────────────────────────
@app.route('/tes/form-pelamar', methods=['GET','POST'])
def tes_form_pelamar():
    """Candidate fills data pelamar form before test starts."""
    if 'tes_code' not in session:
        return redirect(url_for('tes_landing'))
    if request.method == 'POST':
        # Collect all form data
        def get_rows(prefix, fields, max_rows=5):
            rows = []
            for i in range(max_rows):
                row = {f: request.form.get(f'{prefix}_{f}_{i}','').strip() for f in fields}
                if any(row.values()):
                    rows.append(row)
            return rows

        keluarga = get_rows('kel', ['nama','hubungan','lp','usia','pendidikan','pekerjaan'], 10)
        keluarga_menikah = get_rows('kelm', ['nama','hubungan','lp','usia','pendidikan','pekerjaan'], 7)
        pendidikan = get_rows('pend', ['tingkat','nama_sekolah','kota','jurusan','tahun','lulus'], 5)
        pekerjaan = get_rows('kerja', ['perusahaan','jabatan','lama','gaji','alasan'], 5)
        organisasi = get_rows('org', ['nama','jabatan','periode','kota'], 5)
        referensi = get_rows('ref', ['nama','telepon','pekerjaan','hubungan'], 2)
        darurat = get_rows('dar', ['nama','telepon','pekerjaan','hubungan'], 3)

        pertanyaan = {}
        for i in range(1, 15):
            pertanyaan[str(i)] = request.form.get(f'p{i}','').strip()

        form_data = {
            'nama_lengkap': request.form.get('nama_lengkap','').strip(),
            'nik': request.form.get('nik','').strip(),
            'tempat_lahir': request.form.get('tempat_lahir','').strip(),
            'tanggal_lahir': request.form.get('tanggal_lahir','').strip(),
            'jenis_kelamin': request.form.get('jenis_kelamin','').strip(),
            'agama': request.form.get('agama','').strip(),
            'tinggi': request.form.get('tinggi','').strip(),
            'berat': request.form.get('berat','').strip(),
            'no_ktp': request.form.get('no_ktp','').strip(),
            'no_sim': request.form.get('no_sim','').strip(),
            'status_perkawinan': request.form.get('status_perkawinan','').strip(),
            'alamat_ktp': request.form.get('alamat_ktp','').strip(),
            'alamat_tinggal': request.form.get('alamat_tinggal','').strip(),
            'no_hp': request.form.get('no_hp','').strip(),
            'email': request.form.get('email','').strip(),
            'rumah_status': request.form.get('rumah_status','').strip(),
            'kendaraan': request.form.get('kendaraan','').strip(),
            'kendaraan_merk': request.form.get('kendaraan_merk','').strip(),
            'kendaraan_milik': request.form.get('kendaraan_milik','').strip(),
            'sosmed_fb': request.form.get('sosmed_fb','').strip(),
            'sosmed_ig': request.form.get('sosmed_ig','').strip(),
            'sosmed_twitter': request.form.get('sosmed_twitter','').strip(),
            'keluarga': keluarga,
            'keluarga_menikah': keluarga_menikah,
            'pendidikan': pendidikan,
            'pekerjaan': pekerjaan,
            'organisasi': organisasi,
            'referensi': referensi,
            'darurat': darurat,
            'pertanyaan': pertanyaan,
            'deklarasi_nama': request.form.get('deklarasi_nama','').strip(),
        }

        # Validate deklarasi
        if not form_data['deklarasi_nama']:
            return render_template('tes_form_pelamar.html',
                                 posisi=session.get('tes_posisi',''),
                                 religions=RELIGIONS,
                                 error='Harap isi nama lengkap pada bagian deklarasi.',
                                 form_data=form_data)

        # Save to session for use after test
        session['tes_form_data'] = json.dumps(form_data)
        session['tes_nama'] = form_data['nama_lengkap']
        session['tes_nik'] = form_data['nik']
        return redirect(url_for('tes_identitas_confirm'))

    return render_template('tes_form_pelamar.html',
                          posisi=session.get('tes_posisi',''),
                          religions=RELIGIONS,
                          error=None, form_data={})

@app.route('/tes/confirm', methods=['GET','POST'])
def tes_identitas_confirm():
    """Confirm identity and start test."""
    if 'tes_code' not in session or 'tes_form_data' not in session:
        return redirect(url_for('tes_landing'))
    if request.method == 'POST':
        form_data = json.loads(session.get('tes_form_data','{}'))
        nama = form_data.get('nama_lengkap','')
        nik  = form_data.get('nik','')
        tier = session['tes_tier']
        accuracy_pool = list(ACCURACY_PAIRS.get(tier, ACCURACY_PAIRS['operator']))
        random.shuffle(accuracy_pool)
        selected_acc = accuracy_pool[:10]
        math_pool = MATH_QUESTIONS.get(tier, MATH_QUESTIONS['operator'])[:]
        random.shuffle(math_pool)
        selected_math = math_pool[:5]
        logic_pool = LOGIC_QUESTIONS.get(tier, LOGIC_QUESTIONS['operator'])[:]
        random.shuffle(logic_pool)
        selected_logic = logic_pool[:10]
        questions_data = {
            'ketelitian': selected_acc,
            'matematika': selected_math,
            'logika': selected_logic,
        }
        session['tes_section'] = 'ketelitian'
        session['tes_answers'] = {}
        with get_db() as db:
            db.execute("""UPDATE test_codes SET status='active',
                         used_by_nama=?, used_by_nik=?, questions_json=? WHERE code=?""",
                      (nama, nik, json.dumps(questions_data, default=list), session['tes_code']))
        return redirect(url_for('tes_soal'))
    return render_template('tes_identitas.html',
                          posisi=session.get('tes_posisi',''),
                          confirm_mode=True,
                          nama=json.loads(session.get('tes_form_data','{}')).get('nama_lengkap',''))

# ── Auto-delete rejected results after 30 days ─────────────────────────────────
def auto_cleanup_results():
    """Delete rejected test results older than 30 days."""
    try:
        if PG:
            with get_db() as db:
                db.execute("""DELETE FROM test_results
                             WHERE status='active' AND verdict NOT IN ('LULUS','arsip')
                             AND selesai_at < NOW() - INTERVAL '30 days'""")
                db.execute("""DELETE FROM data_pelamar WHERE result_id NOT IN
                             (SELECT id FROM test_results)""")
        else:
            with get_db() as db:
                db.execute("""DELETE FROM test_results
                             WHERE status='active' AND verdict NOT IN ('LULUS','arsip')
                             AND selesai_at < datetime('now','-30 days')""")
                db.execute("""DELETE FROM data_pelamar WHERE result_id NOT IN
                             (SELECT id FROM test_results)""")
    except: pass

# ── Delete test result ─────────────────────────────────────────────────────────
@app.route('/hr/hasil-tes/<int:result_id>/delete', methods=['POST'])
@login_required
@role_required('hr_head','owner')
def delete_hasil_tes(result_id):
    with get_db() as db:
        db.execute("DELETE FROM data_pelamar WHERE result_id=?", (result_id,))
        db.execute("DELETE FROM test_results WHERE id=?", (result_id,))
        log_audit('DELETE_HASIL_TES','test_results',result_id,'Hapus hasil tes')
    flash('Hasil tes berhasil dihapus.', 'success')
    return redirect(url_for('hr_hasil_tes'))

# ── Arsip test result ──────────────────────────────────────────────────────────
@app.route('/hr/hasil-tes/<int:result_id>/arsip', methods=['POST'])
@login_required
@role_required('hr_head','owner')
def arsip_hasil_tes(result_id):
    with get_db() as db:
        db.execute("UPDATE test_results SET status='arsip' WHERE id=?", (result_id,))
        log_audit('ARSIP_HASIL_TES','test_results',result_id,'Arsip hasil tes')
    flash('Hasil tes diarsipkan.', 'success')
    return redirect(url_for('hr_hasil_tes'))

# ── Update checklist ───────────────────────────────────────────────────────────
@app.route('/hr/hasil-tes/<int:result_id>/checklist', methods=['POST'])
@login_required
@role_required('hr_head','owner')
def update_checklist(result_id):
    field = request.form.get('field')
    value = int(request.form.get('value', 0))
    allowed = ['checklist_pdf','checklist_drive','checklist_imported']
    if field not in allowed:
        return jsonify({'ok': False})
    with get_db() as db:
        db.execute(f"UPDATE test_results SET {field}=? WHERE id=?", (value, result_id))
        row = db.fetchone("SELECT checklist_pdf,checklist_drive,checklist_imported FROM test_results WHERE id=?", (result_id,))
    all_done = row and all([row['checklist_pdf'], row['checklist_drive'], row['checklist_imported']])
    return jsonify({'ok': True, 'all_done': all_done})

# ── Terima sebagai Karyawan ────────────────────────────────────────────────────
@app.route('/hr/hasil-tes/<int:result_id>/terima')
@login_required
@role_required('hr_head','owner','hr_staff')
def terima_karyawan(result_id):
    """Pre-fill add staff form with candidate data."""
    with get_db() as db:
        result = db.fetchone("SELECT * FROM test_results WHERE id=?", (result_id,))
        pelamar = db.fetchone("SELECT * FROM data_pelamar WHERE result_id=?", (result_id,))
    if not result:
        flash('Data tidak ditemukan.', 'error')
        return redirect(url_for('hr_hasil_tes'))
    # Store in session for add_staff to pick up
    session['import_from_tes'] = result_id
    flash(f'Data {result["nama_lengkap"]} siap diimport. Harap review semua data sebelum menyimpan.', 'warning')
    return redirect(url_for('add_staff'))

# ── Get pelamar data for import ────────────────────────────────────────────────
@app.route('/api/pelamar-data/<int:result_id>')
@login_required
def get_pelamar_data(result_id):
    with get_db() as db:
        pelamar = db.fetchone("SELECT * FROM data_pelamar WHERE result_id=?", (result_id,))
        result  = db.fetchone("SELECT * FROM test_results WHERE id=?", (result_id,))
    if not pelamar:
        return jsonify({'found': False})

    # Get first emergency contact
    darurat = []
    try:
        darurat = json.loads(pelamar.get('darurat_json') or '[]')
    except: pass
    ec_name  = darurat[0].get('nama','')  if darurat else ''
    ec_phone = darurat[0].get('telepon','') if darurat else ''
    ec_rel   = darurat[0].get('hubungan','') if darurat else ''

    # Clear session import flag after data is fetched
    session.pop('import_from_tes', None)

    return jsonify({
        'found': True,
        'nama_lengkap':       pelamar.get('nama_lengkap') or result.get('nama_lengkap',''),
        'ktp_number':         pelamar.get('nik','') or result.get('nik',''),
        'birth_date':         pelamar.get('tanggal_lahir',''),
        'birth_place':        pelamar.get('tempat_lahir',''),
        'gender':             pelamar.get('jenis_kelamin',''),
        'religion':           pelamar.get('agama',''),
        'address':            pelamar.get('alamat_tinggal',''),
        'phone':              pelamar.get('no_hp',''),
        'emergency_contact':  ec_name,
        'emergency_phone':    ec_phone,
        'emergency_relationship': ec_rel,
    })

# Initialize DB at startup — called here so all functions are defined first
with app.app_context():
    safe_init_db()
    try:
        init_test_tables()
        print("Test tables initialized successfully")
    except Exception as e:
        print(f"Warning: init_test_tables error: {e}")
    # Always-run migrations for new columns on existing DBs
    try:
        if PG:
            url = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
            import psycopg2 as _pg
            _conn = _pg.connect(url)
            _cur = _conn.cursor()
            for _col, _defn in [
                ("questions_json", "TEXT"),
                ("used_by_nama", "VARCHAR(200)"),
                ("used_by_nik", "VARCHAR(20)"),
                ("result_id", "INTEGER"),
                ("status", "VARCHAR(20) DEFAULT 'active'"),
                ("form_data", "TEXT"),
                ("checklist_pdf", "INTEGER DEFAULT 0"),
                ("checklist_drive", "INTEGER DEFAULT 0"),
                ("checklist_imported", "INTEGER DEFAULT 0"),
                ("staff_id", "INTEGER DEFAULT NULL"),
                ("birth_place", "VARCHAR(100) NOT NULL DEFAULT ''"),
            ]:
                try: _cur.execute(f"ALTER TABLE test_codes ADD COLUMN {_col} {_defn}")
                except: pass
            for _col, _defn in [
                ("status", "VARCHAR(20) DEFAULT 'active'"),
                ("form_data", "TEXT"),
                ("checklist_pdf", "INTEGER DEFAULT 0"),
                ("checklist_drive", "INTEGER DEFAULT 0"),
                ("checklist_imported", "INTEGER DEFAULT 0"),
                ("staff_id", "INTEGER DEFAULT NULL"),
            ]:
                try: _cur.execute(f"ALTER TABLE test_results ADD COLUMN {_col} {_defn}")
                except: pass
            # Create data_pelamar if not exists
            try:
                _cur.execute("""CREATE TABLE IF NOT EXISTS data_pelamar (
                    id SERIAL PRIMARY KEY, result_id INTEGER NOT NULL,
                    code VARCHAR(10), nama_lengkap VARCHAR(200), nik VARCHAR(20),
                    tempat_lahir VARCHAR(100), tanggal_lahir VARCHAR(20),
                    jenis_kelamin VARCHAR(20), agama VARCHAR(50),
                    tinggi INTEGER, berat INTEGER, no_ktp VARCHAR(20), no_sim VARCHAR(50),
                    status_perkawinan VARCHAR(30), alamat_ktp TEXT, alamat_tinggal TEXT,
                    no_hp VARCHAR(30), email VARCHAR(100), rumah_status VARCHAR(50),
                    kendaraan VARCHAR(100), kendaraan_merk VARCHAR(100), kendaraan_milik VARCHAR(50),
                    sosmed_fb VARCHAR(100), sosmed_ig VARCHAR(100), sosmed_twitter VARCHAR(100),
                    keluarga_json TEXT, pendidikan_json TEXT, pekerjaan_json TEXT,
                    organisasi_json TEXT, referensi_json TEXT, darurat_json TEXT,
                    pertanyaan_json TEXT, deklarasi_nama VARCHAR(200),
                    created_at TIMESTAMP DEFAULT NOW())""")
            except: pass
            try: _cur.execute("ALTER TABLE staff ADD COLUMN birth_place VARCHAR(100) NOT NULL DEFAULT ''")
            except: pass
            _conn.commit()
            _conn.close()
            print("Migrations applied successfully")
    except Exception as e:
        print(f"Warning: migration error: {e}")

if __name__ == '__main__':
    os.makedirs(os.path.join(os.path.dirname(__file__),'instance'),exist_ok=True)
    print("\n"+"="*52)
    print("  HR Master Data — Mitra Karya Texindo")
    print("="*52)
    print("  Buka browser: http://localhost:5001")
    print("  Owner       : owner / owner123")
    print("  HR Head     : admin / admin123")
    print("  HR Staff    : hrstaff / staff123")
    print("="*52+"\n")
    app.run(debug=False,host='0.0.0.0',port=5001)
