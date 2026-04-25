"""
db_mysql.py - MySQL compatibility layer for NexVision IPTV
"""

import re
import os
import pymysql
import pymysql.cursors


DB_CONFIG = {
    'host':     os.getenv('MYSQL_HOST',     'localhost'),
    'port':     int(os.getenv('MYSQL_PORT', '3306')),
    'user':     os.getenv('MYSQL_USER',     'nexvision'),
    'password': os.getenv('MYSQL_PASSWORD', 'nexvision_pass'),
    'database': os.getenv('MYSQL_DB',       'nexvision'),
    'charset':  'utf8mb4',
    'autocommit': False,
    'connect_timeout': 10,
}

VOD_DB_CONFIG = {
    **DB_CONFIG,
    'database': os.getenv('MYSQL_VOD_DB', 'nexvision_vod'),
}


_INTERVAL_UNIT_MAP = {
    'microseconds': 'MICROSECOND', 'microsecond': 'MICROSECOND',
    'seconds': 'SECOND', 'second': 'SECOND',
    'minutes': 'MINUTE', 'minute': 'MINUTE',
    'hours': 'HOUR', 'hour': 'HOUR',
    'days': 'DAY', 'day': 'DAY',
    'weeks': 'WEEK', 'week': 'WEEK',
    'months': 'MONTH', 'month': 'MONTH',
    'quarters': 'QUARTER', 'quarter': 'QUARTER',
    'years': 'YEAR', 'year': 'YEAR',
}

def _sqlite_interval_to_mysql(m):
    parts = m.group(1).strip().split()
    if len(parts) == 2:
        amount, unit = parts
        mysql_unit = _INTERVAL_UNIT_MAP.get(unit.lower(), unit.upper())
        return f"DATE_ADD(NOW(), INTERVAL {amount} {mysql_unit})"
    return f"DATE_ADD(NOW(), INTERVAL {m.group(1)})"


def _adapt_sql(sql):
    stripped = sql.strip()
    if stripped.upper().startswith('PRAGMA'):
        return 'SELECT 1'

    sql = sql.replace('?', '%s')

    sql = re.sub(r"datetime\('now'\)", 'NOW()', sql, flags=re.IGNORECASE)
    sql = re.sub(r"datetime\('now',\s*'([^']+)'\)", _sqlite_interval_to_mysql, sql, flags=re.IGNORECASE)
    sql = re.sub(r"date\('now'\)", 'CURDATE()', sql, flags=re.IGNORECASE)
    sql = re.sub(
        r"\s*strftime\('([^']+)',\s*([^)]+)\)",
        lambda m: f" UNIX_TIMESTAMP({m.group(2).strip()})" if m.group(1) == '%s' else f" DATE_FORMAT({m.group(2).strip()}, '{m.group(1)}')",
        sql, flags=re.IGNORECASE,
    )

    sql = re.sub(r'\bINTEGER\s+PRIMARY\s+KEY\s+AUTOINCREMENT\b',
                 'INT AUTO_INCREMENT PRIMARY KEY', sql, flags=re.IGNORECASE)

    # MySQL 8: TEXT cannot have DEFAULT values
    sql = re.sub(r"\bTEXT(\s+NOT\s+NULL)?\s+DEFAULT\s+'[^']*'",
                 lambda m: f"TEXT{m.group(1) or ''}", sql, flags=re.IGNORECASE)

    # TEXT PRIMARY KEY -> VARCHAR(255) PRIMARY KEY
    sql = re.sub(r'\bTEXT(\s+NOT\s+NULL)?\s+PRIMARY\s+KEY\b',
                 lambda m: f'VARCHAR(255){m.group(1) or ""} PRIMARY KEY',
                 sql, flags=re.IGNORECASE)

    # TEXT UNIQUE -> VARCHAR(255) UNIQUE
    sql = re.sub(r'\bTEXT(\s+NOT\s+NULL)?\s+UNIQUE\b',
                 lambda m: f'VARCHAR(255){m.group(1) or ""} UNIQUE',
                 sql, flags=re.IGNORECASE)

    # In CREATE TABLE, TEXT columns in PRIMARY KEY or FOREIGN KEY must be VARCHAR(255)
    for kw in ('PRIMARY KEY', 'FOREIGN KEY'):
        for m in re.finditer(rf'\b{kw}\s*\(([^)]+)\)', sql, re.IGNORECASE):
            for col in [c.strip().strip('`') for c in m.group(1).split(',')]:
                sql = re.sub(
                    rf'(`?{re.escape(col)}`?)\s+TEXT(\s)',
                    rf'\1 VARCHAR(255)\2', sql, flags=re.IGNORECASE
                )

    # SQLite conflict clauses
    sql = re.sub(r'\bINSERT\s+OR\s+IGNORE\s+INTO\b', 'INSERT IGNORE INTO', sql, flags=re.IGNORECASE)
    sql = re.sub(r'\bINSERT\s+OR\s+REPLACE\s+INTO\b', 'REPLACE INTO', sql, flags=re.IGNORECASE)

    # Quote reserved word 'key' as column name
    sql = re.sub(r'(?<![`\w])key(?![`\w])', '`key`', sql, flags=re.IGNORECASE)
    sql = re.sub(r'(?i)(PRIMARY|FOREIGN|UNIQUE|INDEX|CONSTRAINT)\s+`key`', r'\1 KEY', sql)

    if re.match(r'\s*CREATE\s+TABLE', sql, re.IGNORECASE):
        if 'ENGINE=' not in sql.upper():
            sql = sql.rstrip().rstrip(';')
            sql += ' ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci'

    return sql


def _split_script(script):
    statements = []
    current = []
    for line in script.splitlines():
        stripped = line.strip()
        if stripped.startswith('--') or stripped == '':
            continue
        current.append(line)
        if stripped.endswith(';'):
            stmt = ' '.join(current).strip()
            if stmt and stmt != ';':
                statements.append(stmt)
            current = []
    if current:
        stmt = ' '.join(current).strip()
        if stmt:
            statements.append(stmt)
    return statements


class MySQLRow:
    def __init__(self, columns, values):
        self._cols = columns
        self._vals = tuple(values)
        self._dict = dict(zip(columns, values))

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._vals[key]
        return self._dict[key]

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)

    def keys(self):
        return list(self._cols)

    def get(self, key, default=None):
        return self._dict.get(key, default)

    def __contains__(self, key):
        return key in self._dict


class MySQLCursorWrapper:
    def __init__(self, raw_cursor):
        self._cur = raw_cursor
        self._cols = [d[0] for d in raw_cursor.description] if raw_cursor.description else []

    def fetchone(self):
        row = self._cur.fetchone()
        return MySQLRow(self._cols, row) if row is not None else None

    def fetchall(self):
        return [MySQLRow(self._cols, row) for row in self._cur.fetchall()]

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount


class MySQLConnection:
    def __init__(self, conn):
        self._conn = conn
        self._last_result = None

    def execute(self, sql, params=()):
        sql = _adapt_sql(sql)
        cur = self._conn.cursor()
        cur.execute(sql, params)
        self._last_result = MySQLCursorWrapper(cur)
        return self._last_result

    def executemany(self, sql, params_list):
        sql = _adapt_sql(sql)
        cur = self._conn.cursor()
        cur.executemany(sql, params_list)
        self._last_result = MySQLCursorWrapper(cur)
        return self._last_result

    def fetchall(self):
        return self._last_result.fetchall() if self._last_result else []

    def fetchone(self):
        return self._last_result.fetchone() if self._last_result else None

    @property
    def lastrowid(self):
        return self._last_result.lastrowid if self._last_result else None

    @property
    def rowcount(self):
        return self._last_result.rowcount if self._last_result else 0

    def executescript(self, script):
        cur = self._conn.cursor()
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
        cur.execute("SET SESSION sql_mode='NO_ENGINE_SUBSTITUTION'")
        for stmt in _split_script(script):
            adapted = _adapt_sql(stmt)
            if adapted.strip().upper() == 'SELECT 1':
                continue
            try:
                cur = self._conn.cursor()
                cur.execute(adapted)
            except (pymysql.err.OperationalError, pymysql.err.ProgrammingError) as e:
                if e.args[0] not in (1050, 1060, 1061, 1091, 1824):
                    raise
        self._conn.cursor().execute("SET FOREIGN_KEY_CHECKS=1")

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self._conn.rollback()
        else:
            self._conn.commit()
        self.close()


def add_column_if_missing(conn, table, column, typedef):
    result = conn.execute(
        "SELECT COUNT(*) FROM information_schema.COLUMNS "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s",
        (table, column)
    ).fetchone()
    if result[0] == 0:
        conn.execute(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {typedef}")
        conn.commit()


def get_mysql_db(config=None):
    cfg = config or DB_CONFIG
    raw = pymysql.connect(**cfg)
    with raw.cursor() as cur:
        cur.execute("SET SESSION sql_mode='NO_ENGINE_SUBSTITUTION'")
        cur.execute("SET FOREIGN_KEY_CHECKS=0")
    return MySQLConnection(raw)


def get_vod_mysql_db():
    return get_mysql_db(VOD_DB_CONFIG)
