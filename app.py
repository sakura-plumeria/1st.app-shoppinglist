from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import sqlite3
from contextlib import closing
from datetime import datetime
import secrets

app = Flask(__name__)
app.secret_key = "change-me"

DATABASE = "app.db"
UNDO_TTL_SEC = 10  # Undoの有効時間（秒）


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with closing(get_db()) as db:
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item TEXT NOT NULL,
                category TEXT NOT NULL,
                purchased INTEGER NOT NULL DEFAULT 0,
                added_at TEXT NOT NULL
            )
            """
        )
        db.commit()


# Flask 3系: 起動時に一度だけDBを初期化
with app.app_context():
    init_db()


# ---- Undo関連の小さなヘルパ ----

def _get_undo():
    return session.get("undo")


def _clear_undo():
    session.pop("undo", None)


def _finalize_undo_now():
    # 今保持しているUndoを即時確定（購入確定=削除）。別の「買ったよ」を押した時に使用。
    info = _get_undo()
    if not info:
        return
    item_id = int(info.get("item_id", 0))
    token = info.get("token")
    if not item_id or not token:
        _clear_undo()
        return
    with closing(get_db()) as db:
        # まだ存在し、かつpurchased=1なら削除
        db.execute("DELETE FROM items WHERE id=? AND purchased=1", (item_id,))
        db.commit()
    _clear_undo()


def _finalize_undo_if_expired():
    """ページ表示時に、期限切れのUndoがあればサーバ側でも確定（削除）する。"""
    info = _get_undo()
    if not info:
        return
    now = datetime.now().timestamp()
    started = float(info.get("at", 0))
    if now - started > UNDO_TTL_SEC:
        _finalize_undo_now()


@app.route("/", methods=["GET", "POST"])
def index():
    # ページ到達時に期限切れUndoを掃除
    _finalize_undo_if_expired()

    if request.method == "POST":
        # 追加
        if (
            "item" in request.form
            and "category" in request.form
            and "buy" not in request.form
            and "delete" not in request.form
        ):
            item = (request.form.get("item") or "").strip()
            category = (request.form.get("category") or "未分類").strip()
            if item:
                with closing(get_db()) as db:
                    db.execute(
                        "INSERT INTO items (item, category, purchased, added_at) VALUES (?,?,0,?)",
                        (item, category, datetime.now().strftime("%Y-%m-%d %H:%M")),
                    )
                    db.commit()
            return redirect(url_for("index"))

        # 手動削除
        if "delete" in request.form:
            item_id = int(request.form.get("delete"))
            with closing(get_db()) as db:
                db.execute("DELETE FROM items WHERE id=?", (item_id,))
                db.commit()
            # 関連するUndoが同じIDなら無効化
            info = _get_undo()
            if info and int(info.get("item_id", 0)) == item_id:
                _clear_undo()
            return redirect(url_for("index"))

        # 買ったよ
        if "buy" in request.form:
            item_id = int(request.form.get("buy"))
            # 既存のUndoがあれば即確定してから新しいUndoをセット
            _finalize_undo_now()
            with closing(get_db()) as db:
                row = db.execute("SELECT purchased FROM items WHERE id=?", (item_id,)).fetchone()
                if row and int(row["purchased"]) == 0:
                    db.execute("UPDATE items SET purchased=1 WHERE id=?", (item_id,))
                    db.commit()
                    session["undo"] = {
                        "type": "buy",
                        "item_id": item_id,
                        "token": secrets.token_urlsafe(16),
                        "at": datetime.now().timestamp(),
                    }
            return redirect(url_for("index"))

    # --- GET: 一覧表示（購入済みは基本出さないが、直前の1件だけは表示され得る） ---
    with closing(get_db()) as db:
        rows = db.execute("SELECT * FROM items ORDER BY category COLLATE NOCASE ASC, datetime(added_at) DESC").fetchall()
    rows = [dict(r) for r in rows]

    # 直前のUndoがある場合、そのアイテムは purchased=1 のまま描画される（10秒だけ）
    categorized_items = {}
    for r in rows:
        cat = r["category"]
        categorized_items.setdefault(cat, []).append(r)

    # Undoバーの情報
    undo = _get_undo()
    undo_available = False
    undo_item_id = None
    undo_token = None
    undo_remaining_ms = 0
    if undo:
        started = float(undo.get("at", 0))
        now = datetime.now().timestamp()
        remain = max(0, UNDO_TTL_SEC - (now - started))
        if remain > 0:
            undo_available = True
            undo_item_id = int(undo.get("item_id"))
            undo_token = undo.get("token")
            undo_remaining_ms = int(remain * 1000)
        else:
            _finalize_undo_now()

    return render_template(
        "index.html",
        categorized_items=categorized_items,
        undo_available=undo_available,
        undo_item_id=undo_item_id,
        undo_token=undo_token,
        undo_remaining_ms=undo_remaining_ms,
    )


@app.route("/undo", methods=["POST"])
def undo():
    undo = _get_undo()
    if not undo:
        return redirect(url_for("index"))

    token = request.form.get("token")
    if not token or token != undo.get("token"):
        return redirect(url_for("index"))

    started = float(undo.get("at", 0))
    now = datetime.now().timestamp()
    if now - started > UNDO_TTL_SEC:
        _finalize_undo_now()
        return redirect(url_for("index"))

    item_id = int(undo.get("item_id"))
    with closing(get_db()) as db:
        # 購入フラグを元に戻す
        db.execute("UPDATE items SET purchased=0 WHERE id=?", (item_id,))
        db.commit()

    _clear_undo()
    return redirect(url_for("index"))


@app.route("/finalize_purchase", methods=["POST"])
def finalize_purchase():
    # ロントの10秒タイマーから呼ばれて、購入を最終確定（=削除）
    undo = _get_undo()
    item_id = request.form.get("item_id")
    token = request.form.get("token")

    if not (undo and item_id and token):
        return ("", 204)

    if token != undo.get("token") or int(item_id) != int(undo.get("item_id")):
        return ("", 204)

    with closing(get_db()) as db:
        db.execute("DELETE FROM items WHERE id=? AND purchased=1", (int(item_id),))
        db.commit()

    _clear_undo()
    return ("", 204)


if __name__ == "__main__":
    app.run(debug=True)