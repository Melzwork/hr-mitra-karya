from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime, date, timedelta
from functools import wraps
import os, hashlib, json, calendar

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
app.secret_key = os.environ.get('SECRET_KEY', 'hr_mitra_karya_2026_secret')

# Custom Jinja2 filter: format date safely for both SQLite (string) and PostgreSQL (datetime)
@app.template_filter('datestr')
def datestr_filter(value):
    if value is None: return '—'
    if hasattr(value, 'strftime'): return value.strftime('%Y-%m-%d')
    return str(value)[:10]

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
    "Pengawas": ["Pengawas Lapangan", "Kabag Dyeing", "Kabag Finishing"],
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
            birth_date VARCHAR(20) NOT NULL, gender VARCHAR(20) NOT NULL,
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
                gender TEXT NOT NULL, religion TEXT NOT NULL DEFAULT 'Islam',
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
            db.fetchall("""INSERT INTO staff
                (emp_id,full_name,ktp_number,birth_date,gender,religion,
                 address,rt_rw,kelurahan,kecamatan,kota,provinsi,
                 phone,position,department,education,
                 emergency_contact,emergency_relationship,emergency_phone,created_by)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (emp_id,request.form['full_name'],ktp,
                 request.form['birth_date'],request.form['gender'],request.form['religion'],
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
    return render_template('add_staff.html', departments=DEPARTMENTS_POSITIONS,
                          provinces=PROVINCES, religions=RELIGIONS)

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
            db.fetchall("""UPDATE staff SET full_name=?,birth_date=?,gender=?,religion=?,
                         address=?,rt_rw=?,kelurahan=?,kecamatan=?,kota=?,provinsi=?,
                         phone=?,position=?,department=?,education=?,
                         emergency_contact=?,emergency_relationship=?,emergency_phone=?,
                         updated_by=?,updated_at=datetime('now','localtime') WHERE id=?""",
                      (request.form['full_name'],request.form['birth_date'],request.form['gender'],
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
            # Check if users table already has data
            count = db.fetchval("SELECT COUNT(*) FROM users")
            if count and count > 0:
                print("Database already initialized — skipping init_db()")
                return
    except:
        pass  # Table doesn't exist yet — run init
    try:
        init_db()
        print("Database initialized successfully")
    except Exception as e:
        print(f"Warning: init_db error: {e}")

with app.app_context():
    safe_init_db()

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
