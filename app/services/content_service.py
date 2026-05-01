"""Content pages and items (hotel info, menus, galleries, etc.)."""
import os
import uuid
from flask import jsonify, current_app
from ..extensions import get_db
from ..config import UPLOAD_DIR


def _bump_stamp(conn):
    conn.execute(
        "INSERT OR REPLACE INTO settings (key, value) "
        "VALUES ('config_stamp', CAST(strftime('%s','now') AS TEXT))"
    )


def list_pages():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM content_pages ORDER BY name"
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def get_page(pid: int):
    conn = get_db()
    page = conn.execute(
        "SELECT * FROM content_pages WHERE id=?", (pid,)
    ).fetchone()
    if not page:
        conn.close()
        return jsonify({'error': 'Not found'}), 404
    result = dict(page)
    # Include items with gallery images so TV client can render the overlay
    item_rows = conn.execute(
        "SELECT * FROM content_items WHERE page_id=? ORDER BY sort_order, id", (pid,)
    ).fetchall()
    items = []
    for ir in item_rows:
        item = dict(ir)
        img_rows = conn.execute(
            "SELECT id, url, position, fit, sort_order FROM content_item_images "
            "WHERE item_id=? ORDER BY sort_order, id", (item['id'],)
        ).fetchall()
        item['images'] = [dict(r) for r in img_rows]
        items.append(item)
    result['items'] = items
    conn.close()
    return jsonify(result)


def create_page(d: dict):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO content_pages (name, group_name, template, active) "
        "VALUES (?,?,?,?)",
        (d['name'], d.get('group_name', 'Hotel'),
         d.get('template', 'Default'), d.get('active', 1)),
    )
    _bump_stamp(conn)
    conn.commit()
    page = dict(conn.execute(
        "SELECT * FROM content_pages WHERE id=?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return jsonify(page), 201


def update_page(pid: int, d: dict):
    conn = get_db()
    conn.execute(
        "UPDATE content_pages SET name=?, group_name=?, template=?, active=? "
        "WHERE id=?",
        (d['name'], d.get('group_name', 'Hotel'),
         d.get('template', 'Default'), d.get('active', 1), pid),
    )
    _bump_stamp(conn)
    conn.commit()
    page = dict(conn.execute(
        "SELECT * FROM content_pages WHERE id=?", (pid,)
    ).fetchone())
    conn.close()
    return jsonify(page)


def delete_page(pid: int):
    conn = get_db()
    conn.execute("DELETE FROM content_pages WHERE id=?", (pid,))
    _bump_stamp(conn)
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def list_items(pid: int):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM content_items WHERE page_id=? ORDER BY sort_order, id",
        (pid,),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def list_items_full(pid: int):
    conn = get_db()
    item_rows = conn.execute(
        "SELECT * FROM content_items WHERE page_id=? ORDER BY sort_order, id", (pid,)
    ).fetchall()
    items = []
    for ir in item_rows:
        item = dict(ir)
        img_rows = conn.execute(
            "SELECT id, url, position, fit, sort_order FROM content_item_images "
            "WHERE item_id=? ORDER BY sort_order, id", (item['id'],)
        ).fetchall()
        item['images'] = [dict(r) for r in img_rows]
        items.append(item)
    conn.close()
    return jsonify(items)


def create_item(pid: int, d: dict):
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO content_items (page_id, title, description, photo_url, sort_order, active, content_html) "
        "VALUES (?,?,?,?,?,?,?)",
        (pid, d.get('title', ''), d.get('description', d.get('body', '')),
         d.get('photo_url', ''), d.get('sort_order', 0), d.get('active', 1),
         d.get('content_html', '')),
    )
    conn.commit()
    item = dict(conn.execute(
        "SELECT * FROM content_items WHERE id=?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return jsonify(item), 201


def update_item(iid: int, d: dict):
    conn = get_db()
    conn.execute(
        "UPDATE content_items SET title=?, description=?, photo_url=?, "
        "sort_order=?, active=?, content_html=? WHERE id=?",
        (d.get('title', ''), d.get('description', d.get('body', '')),
         d.get('photo_url', ''), d.get('sort_order', 0), d.get('active', 1),
         d.get('content_html', ''), iid),
    )
    conn.commit()
    item = dict(conn.execute(
        "SELECT * FROM content_items WHERE id=?", (iid,)
    ).fetchone())
    conn.close()
    return jsonify(item)


def delete_item(iid: int):
    conn = get_db()
    conn.execute("DELETE FROM content_items WHERE id=?", (iid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def _save_upload(file, subfolder='content'):
    allowed = current_app.config.get('ALLOWED_IMAGE_EXTS', {'png','jpg','jpeg','gif','webp'})
    ext = os.path.splitext(file.filename)[1].lower().lstrip('.')
    if ext not in allowed:
        return None, 'Invalid file type'
    dest_dir = UPLOAD_DIR / subfolder
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}.{ext}"
    file.save(str(dest_dir / filename))
    return f'/uploads/{subfolder}/{filename}', None


def upload_item_image(iid: int, request):
    f = request.files.get('image')
    if not f:
        return jsonify({'error': 'No image'}), 400
    url, err = _save_upload(f)
    if err:
        return jsonify({'error': err}), 400
    conn = get_db()
    conn.execute("UPDATE content_items SET photo_url=? WHERE id=?", (url, iid))
    conn.commit()
    conn.close()
    return jsonify({'url': url})


def get_gallery(iid: int):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM content_item_images WHERE item_id=? ORDER BY sort_order, id",
        (iid,),
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


def add_gallery_url(iid: int, d: dict):
    url = d.get('url', '').strip()
    if not url:
        return jsonify({'error': 'url required'}), 400
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO content_item_images (item_id, url) VALUES (?,?)",
        (iid, url),
    )
    conn.commit()
    img = dict(conn.execute(
        "SELECT * FROM content_item_images WHERE id=?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return jsonify(img), 201


def upload_gallery_image(iid: int, request):
    f = request.files.get('image')
    if not f:
        return jsonify({'error': 'No image'}), 400
    url, err = _save_upload(f, 'gallery')
    if err:
        return jsonify({'error': err}), 400
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO content_item_images (item_id, url) VALUES (?,?)", (iid, url)
    )
    conn.commit()
    img = dict(conn.execute(
        "SELECT * FROM content_item_images WHERE id=?", (cur.lastrowid,)
    ).fetchone())
    conn.close()
    return jsonify(img), 201


def delete_gallery_image(imgid: int):
    conn = get_db()
    conn.execute("DELETE FROM content_item_images WHERE id=?", (imgid,))
    conn.commit()
    conn.close()
    return jsonify({'ok': True})


def update_gallery_image(imgid: int, d: dict):
    conn = get_db()
    conn.execute(
        "UPDATE content_item_images SET position=?, fit=?, sort_order=? WHERE id=?",
        (d.get('position', 'center center'), d.get('fit', 'cover'),
         d.get('sort_order', 0), imgid),
    )
    conn.commit()
    img = dict(conn.execute(
        "SELECT * FROM content_item_images WHERE id=?", (imgid,)
    ).fetchone())
    conn.close()
    return jsonify(img)
