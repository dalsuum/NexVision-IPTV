from flask import jsonify
from ..extensions import get_db


def list_birthdays():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM birthdays ORDER BY strftime('%m-%d', birth_date)"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def get_today():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM birthdays "
        "WHERE strftime('%m-%d', birth_date) = strftime('%m-%d', 'now')"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def create_birthday(d: dict):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO birthdays (guest_name, birth_date, room_number, message) VALUES (?,?,?,?)",
        (d.get('guest_name') or d.get('name', ''), d['birth_date'],
         d.get('room_number', ''), d.get('message') or d.get('note', '')),
    )
    conn.commit()
    b = dict(conn.execute(
        "SELECT * FROM birthdays WHERE id=?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return jsonify(b), 201


def update_birthday(bid: int, d: dict):
    conn = get_db()
    conn.execute(
        "UPDATE birthdays SET guest_name=?, birth_date=?, room_number=?, message=? WHERE id=?",
        (d.get('guest_name') or d.get('name', ''), d['birth_date'],
         d.get('room_number', ''), d.get('message') or d.get('note', ''), bid),
    )
    conn.commit()
    b = dict(conn.execute(
        "SELECT * FROM birthdays WHERE id=?", (bid,)
    ).fetchone())
    conn.close()
    return jsonify(b)


def delete_birthday(bid: int):
    conn = get_db()
    conn.execute("DELETE FROM birthdays WHERE id=?", (bid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})
