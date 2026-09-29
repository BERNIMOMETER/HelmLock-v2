import os
import sqlite3
from contextlib import contextmanager

LOCAL_MODE = os.environ.get("LOCAL_MODE", "false").lower() in {"1", "true", "yes", "on"}
LOCAL_DB_PATH = os.environ.get("LOCAL_DB_PATH", "/app/data/helmlock.sqlite3")
_supabase = None


def _init_local():
    os.makedirs(os.path.dirname(LOCAL_DB_PATH) or ".", exist_ok=True)
    with sqlite3.connect(LOCAL_DB_PATH) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS lockers (locker_number INTEGER PRIMARY KEY, status TEXT NOT NULL DEFAULT 'available');
        CREATE TABLE IF NOT EXISTS transactions (
            id TEXT PRIMARY KEY, locker_number INTEGER NOT NULL, payment_method TEXT NOT NULL,
            amount INTEGER NOT NULL, pin TEXT NOT NULL, card_uid TEXT, status TEXT NOT NULL,
            rented_at TEXT NOT NULL, expires_at TEXT NOT NULL, retrieved_at TEXT,
            overtime_paid INTEGER NOT NULL DEFAULT 0, overtime_amount INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS nfc_cards (
            card_uid TEXT PRIMARY KEY, balance INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'idle', updated_at TEXT
        );
        """)
        db.executemany("INSERT OR IGNORE INTO lockers(locker_number, status) VALUES (?, 'available')", [(i,) for i in range(1, 13)])


@contextmanager
def _db():
    _init_local()
    db = sqlite3.connect(LOCAL_DB_PATH)
    db.row_factory = sqlite3.Row
    try:
        yield db
        db.commit()
    finally:
        db.close()


def get_client():
    if LOCAL_MODE:
        return None
    global _supabase
    if _supabase:
        return _supabase
    url, key = os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_KEY", "")
    if url and key:
        from supabase import create_client
        _supabase = create_client(url, key)
    return _supabase


def db_get_all_lockers():
    if LOCAL_MODE:
        with _db() as db:
            return {r["locker_number"]: r["status"] for r in db.execute("SELECT locker_number,status FROM lockers")}
    sb = get_client()
    if not sb: return {}
    try:
        res = sb.table("lockers").select("locker_number, status").execute()
        return {r["locker_number"]: r["status"] for r in res.data}
    except Exception as e:
        print(f"[DB] db_get_all_lockers error: {e}"); return {}


def db_get_locker_status(locker_number):
    if LOCAL_MODE:
        with _db() as db:
            row = db.execute("SELECT status FROM lockers WHERE locker_number=?", (int(locker_number),)).fetchone()
            return row["status"] if row else None
    sb = get_client()
    if not sb: return None
    try: return sb.table("lockers").select("status").eq("locker_number", locker_number).single().execute().data["status"]
    except Exception as e: print(f"[DB] db_get_locker_status error: {e}"); return None


def db_set_locker(locker_number, status):
    if LOCAL_MODE:
        with _db() as db:
            return db.execute("UPDATE lockers SET status=? WHERE locker_number=?", (status, int(locker_number))).rowcount == 1
    sb = get_client()
    if not sb: return False
    try: return bool(sb.table("lockers").update({"status": status}).eq("locker_number", int(locker_number)).execute().data)
    except Exception as e: print(f"[DB] db_set_locker error: {e}"); return False


def db_insert_transaction(data):
    if LOCAL_MODE:
        from datetime import datetime, timezone
        from uuid import uuid4
        row = {"id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat(), "card_uid": None, "retrieved_at": None, "overtime_paid": 0, "overtime_amount": 0, **data}
        with _db() as db:
            db.execute("""INSERT INTO transactions
                (id,locker_number,payment_method,amount,pin,card_uid,status,rented_at,expires_at,retrieved_at,overtime_paid,overtime_amount,created_at)
                VALUES (:id,:locker_number,:payment_method,:amount,:pin,:card_uid,:status,:rented_at,:expires_at,:retrieved_at,:overtime_paid,:overtime_amount,:created_at)""", row)
        return True
    sb = get_client()
    if not sb: return False
    try: sb.table("transactions").insert(data).execute(); return True
    except Exception as e: print(f"[DB] db_insert_transaction error: {e}"); return False


def db_get_transaction_by_pin(pin):
    if LOCAL_MODE:
        with _db() as db:
            row = db.execute("SELECT * FROM transactions WHERE pin=? AND status IN ('active','expired') ORDER BY created_at DESC LIMIT 1", (pin,)).fetchone()
            return dict(row) if row else None
    sb = get_client()
    if not sb: return None
    try:
        res = sb.table("transactions").select("*").eq("pin", pin).in_("status", ["active", "expired"]).order("created_at", desc=True).limit(1).execute()
        if not res.data: return None
        row = res.data[0]; row["overtime_paid"] = bool(row.get("overtime_paid")); row["overtime_amount"] = row.get("overtime_amount") or 0; return row
    except Exception as e: print(f"[DB] db_get_transaction_by_pin error: {e}"); return None


def db_update_transaction(tx_id, fields):
    if LOCAL_MODE:
        allowed = {k: v for k, v in fields.items() if k in {"locker_number","payment_method","amount","pin","card_uid","status","rented_at","expires_at","retrieved_at","overtime_paid","overtime_amount"}}
        if not allowed: return False
        with _db() as db:
            return db.execute(f"UPDATE transactions SET {', '.join(f'{k}=?' for k in allowed)} WHERE id=?", (*allowed.values(), tx_id)).rowcount == 1
    sb = get_client()
    if not sb: return False
    try: sb.table("transactions").update(fields).eq("id", tx_id).execute(); return True
    except Exception as e: print(f"[DB] db_update_transaction error: {e}"); return False


def db_get_overdue_transactions():
    from services.locker_service import now_utc
    if LOCAL_MODE:
        with _db() as db:
            return [dict(r) for r in db.execute("SELECT id,locker_number,expires_at FROM transactions WHERE status='active' AND expires_at < ?", (now_utc().isoformat(),))]
    sb = get_client()
    if not sb: return []
    try: return sb.table("transactions").select("id, locker_number, expires_at").eq("status", "active").lt("expires_at", now_utc().isoformat()).execute().data or []
    except Exception as e: print(f"[DB] db_get_overdue_transactions error: {e}"); return []


def db_get_nfc_card(uid):
    if not LOCAL_MODE: return None
    with _db() as db:
        row = db.execute("SELECT * FROM nfc_cards WHERE card_uid=?", (uid,)).fetchone(); return dict(row) if row else None


def db_upsert_nfc_card(uid, fields):
    if not LOCAL_MODE: return False
    if db_get_nfc_card(uid): return db_update_nfc_card(uid, fields)
    data = {"balance": 0, "status": "idle", "updated_at": None, **fields}
    with _db() as db: db.execute("INSERT INTO nfc_cards(card_uid,balance,status,updated_at) VALUES (?,?,?,?)", (uid, data["balance"], data["status"], data["updated_at"]))
    return True


def db_update_nfc_card(uid, fields):
    if not LOCAL_MODE: return False
    allowed = {k: v for k, v in fields.items() if k in {"balance", "status", "updated_at"}}
    if not allowed: return False
    with _db() as db: return db.execute(f"UPDATE nfc_cards SET {', '.join(f'{k}=?' for k in allowed)} WHERE card_uid=?", (*allowed.values(), uid)).rowcount == 1


def db_get_active_transaction_by_card(uid):
    if not LOCAL_MODE: return None
    with _db() as db:
        row = db.execute("SELECT * FROM transactions WHERE card_uid=? AND status='active' LIMIT 1", (uid,)).fetchone(); return dict(row) if row else None
