"""One pooled connection per request. Always parameterised queries (Architecture.md section 10)."""
import mysql.connector
from mysql.connector import pooling
from flask import g
import config

_pool = None

def _get_pool():
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(pool_name="parkwise", pool_size=8, autocommit=True, **config.DB)
    return _pool

def conn():
    if "conn" not in g:
        g.conn = _get_pool().get_connection()
        g.conn.autocommit = True      # stored procedures manage their own transactions
    return g.conn

def close_conn(_exc=None):
    c = g.pop("conn", None)
    if c is not None:
        c.close()

def rows(sql, params=()):
    cur = conn().cursor(dictionary=True)
    try:
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        cur.close()

def one(sql, params=()):
    r = rows(sql, params)
    return r[0] if r else None

def execute(sql, params=()):
    cur = conn().cursor()
    try:
        cur.execute(sql, params)
        conn().commit()                      # belt and braces: never lose a write
        return cur.lastrowid, cur.rowcount
    finally:
        cur.close()

def call(name, args=()):
    """Call a stored procedure. Returns (out_args_tuple, list_of_result_sets_as_dicts)."""
    cur = conn().cursor()                 # plain cursor: callproc returns the argument tuple
    try:
        out = tuple(cur.callproc(name, list(args)))
        sets = []
        for r in cur.stored_results():
            cols = [d[0] for d in r.description]
            sets.append([dict(zip(cols, row)) for row in r.fetchall()])
        return out, sets
    finally:
        cur.close()

def as_admin(user_id):
    """Set @app_user_id so audit triggers record who made the change."""
    execute("SET @app_user_id = %s", (user_id,))

def clear_admin():
    execute("SET @app_user_id = NULL")
