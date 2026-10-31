
import os
import sqlite3
import uuid
import hmac
import secrets
import shutil

from functools import wraps
from datetime import date

from flask import (
    Flask, jsonify, render_template, request,
    send_from_directory, session, redirect, url_for
)

import analysis
import generate_data
import bbmp_sync


app = Flask(__name__)

# ---------------------------------------------------------------------------
# SECURITY CONFIGURATION
# ---------------------------------------------------------------------------

# Local demo configuration.
# Change this secret and password before deploying publicly.
app.secret_key = os.environ.get(
    "CITYMEMORY_SECRET_KEY",
    "citymemory-local-demo-secret-change-before-deployment"
)

ADMIN_USERNAME = os.environ.get(
    "CITYMEMORY_ADMIN_USER", "Renuka"
)

ADMIN_PASSWORD = os.environ.get(
    "CITYMEMORY_ADMIN_PASSWORD", "1112006"
)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get(
        "CITYMEMORY_COOKIE_SECURE", "0"
    ) == "1",
    PERMANENT_SESSION_LIFETIME=1800,
    MAX_CONTENT_LENGTH=6 * 1024 * 1024
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _get_upload_folder():
    custom = os.environ.get("CITYMEMORY_UPLOAD_FOLDER")
    if custom:
        return custom

    local_upload = os.path.join(BASE_DIR, "private_uploads")
    is_serverless = bool(
        os.environ.get("VERCEL")
        or os.environ.get("VERCEL_ENV")
        or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    )

    if is_serverless or not os.access(BASE_DIR, os.W_OK):
        import tempfile
        return os.path.join(tempfile.gettempdir(), "private_uploads")

    return local_upload


# Photos are stored outside the public static folder.
UPLOAD_FOLDER = _get_upload_folder()

LEGACY_UPLOAD_FOLDER = os.path.join(
    BASE_DIR, "static", "uploads"
)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024

try:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
except OSError:
    pass

DB = generate_data.get_db_path()

if not os.path.exists(DB):
    print(f"Seeding simulated data to {DB}...")
    try:
        generate_data.generate(db_path=DB)
    except Exception as _e:
        print(f"Warning: Database seeding failed: {_e}")


# ---------------------------------------------------------------------------
# DATABASE MIGRATIONS
# ---------------------------------------------------------------------------

def _migrate_db():
    if not os.path.exists(DB):
        return

    try:
        con = sqlite3.connect(DB)
        try:
            cols = {
                row[1]
                for row in con.execute(
                    "PRAGMA table_info(complaints)"
                )
            }

            if not cols:
                return

            if "photo_path" not in cols:
                con.execute(
                    "ALTER TABLE complaints ADD COLUMN photo_path TEXT"
                )
                print("Migration: added photo_path column.")

            if "reference_id" not in cols:
                con.execute(
                    "ALTER TABLE complaints ADD COLUMN reference_id TEXT"
                )
                print("Migration: added reference_id column.")

            # Give all previous complaints a reference ID too.
            rows = con.execute("""
                SELECT id
                FROM complaints
                WHERE reference_id IS NULL OR reference_id = ''
            """).fetchall()

            for row in rows:
                complaint_id = int(row[0])
                reference_id = f"CM-{complaint_id:06d}"

                con.execute(
                    """
                    UPDATE complaints
                    SET reference_id = ?
                    WHERE id = ?
                    """,
                    (reference_id, complaint_id)
                )

            con.commit()
        finally:
            con.close()
    except Exception as _e:
        print(f"Notice: Database migration check skipped: {_e}")


def _migrate_private_uploads():
    """
    Move old uploaded photos outside static/uploads.
    Update database paths to protected admin photo URLs.
    """

    try:
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    except OSError:
        pass

    if os.path.isdir(LEGACY_UPLOAD_FOLDER):
        try:
            for filename in os.listdir(LEGACY_UPLOAD_FOLDER):
                source = os.path.join(
                    LEGACY_UPLOAD_FOLDER, filename
                )
                destination = os.path.join(
                    UPLOAD_FOLDER, filename
                )

                if os.path.isfile(source):
                    if not os.path.exists(destination):
                        shutil.move(source, destination)
                    else:
                        os.remove(source)

            try:
                os.rmdir(LEGACY_UPLOAD_FOLDER)
            except OSError:
                pass
        except OSError:
            pass

    if not os.path.exists(DB):
        return

    try:
        con = sqlite3.connect(DB)
        try:
            rows = con.execute("""
                SELECT id, photo_path
                FROM complaints
                WHERE photo_path LIKE '/static/uploads/%'
            """).fetchall()

            for complaint_id, old_path in rows:
                filename = os.path.basename(old_path)

                if not filename:
                    continue

                private_path = os.path.join(
                    UPLOAD_FOLDER, filename
                )

                if os.path.isfile(private_path):
                    new_path = f"/admin/photo/{filename}"

                    con.execute(
                        """
                        UPDATE complaints
                        SET photo_path = ?
                        WHERE id = ?
                        """,
                        (new_path, complaint_id)
                    )

            con.commit()
        finally:
            con.close()
    except Exception as _e:
        print(f"Notice: Upload migration skipped: {_e}")


_migrate_db()
_migrate_private_uploads()


# ---------------------------------------------------------------------------
# AUTHENTICATION AND CSRF
# ---------------------------------------------------------------------------

def _csrf_token():

    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)

    return session["csrf_token"]


def _valid_csrf():

    submitted = (
        request.headers.get("X-CSRF-Token")
        or request.form.get("csrf_token")
    )

    expected = session.get("csrf_token")

    return (
        bool(submitted)
        and bool(expected)
        and hmac.compare_digest(submitted, expected)
    )


def admin_required(view):

    @wraps(view)
    def wrapped(*args, **kwargs):

        if not session.get("is_admin"):

            if request.path.startswith("/api/"):
                return jsonify({
                    "error": "Administrator login required."
                }), 401

            return redirect(url_for("admin_login"))

        return view(*args, **kwargs)

    return wrapped


# ---------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------
def _find_bbmp_work_orders(asset, limit=10):
    """
    Find potential BBMP work-order matches for an inferred asset.
    These are suggestions, not verified maintenance links.
    """
    if not os.path.exists(DB):
        return []

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    try:
        table_exists = con.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            AND name = 'bbmp_work_orders'
        """).fetchone()

        if not table_exists:
            return []

        rows = con.execute("""
            SELECT
                work_order_id,
                ward,
                work_description,
                amount,
                net_amount,
                bill_reference
            FROM bbmp_work_orders
            WHERE work_description IS NOT NULL
              AND TRIM(work_description) != ''
        """).fetchall()

        if not rows:
            return []

        complaint_texts = [
            str(item.get("text", ""))
            for item in asset.get("_items", [])
            if item.get("text")
        ]

        if not complaint_texts:
            return []

        query = " ".join(complaint_texts)

        descriptions = [
            str(row["work_description"])
            for row in rows
        ]

        scores = analysis.text_similarity(query, descriptions)

        results = []

        for row, score in zip(rows, scores):
            results.append({
                "work_order_id": row["work_order_id"],
                "ward": row["ward"],
                "work_description": row["work_description"],
                "amount": row["amount"],
                "net_amount": row["net_amount"],
                "bill_reference": row["bill_reference"],
                "similarity_score": round(float(score), 3),
                "match_type": "Potential match - unverified"
            })

        results.sort(
            key=lambda item: item["similarity_score"],
            reverse=True
        )

        return results[:limit]

    finally:
        con.close()

def _assets():
    return analysis.build_assets(
        analysis.load_complaints(DB)
    )


def _allowed_file(filename):

    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower()
        in ALLOWED_EXTENSIONS
    )


def _bbmp_workorder_count():
    if not os.path.exists(DB):
        return 0

    con = sqlite3.connect(DB)

    try:
        table_exists = con.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            AND name = 'bbmp_work_orders'
        """).fetchone()

        if not table_exists:
            return 0

        result = con.execute(
            "SELECT COUNT(*) FROM bbmp_work_orders"
        ).fetchone()

        return result[0]

    finally:
        con.close()


def _normalize_category(value):
    """Normalize citizen category labels to consistent database values."""

    category = (value or "other").strip().lower()

    aliases = {
        "pothole": "pothole",
        "pothole / damaged road": "pothole",
        "road / pothole": "pothole",
        "damaged road": "pothole",
        "drainage": "drainage",
        "drainage / waterlogging": "drainage",
        "drain": "drainage",
        "streetlight": "streetlight",
        "street light": "streetlight",
        "garbage": "other",
        "garbage / waste": "other",
        "footpath": "footpath",
        "other": "other"
    }

    return aliases.get(category, "other")


# ---------------------------------------------------------------------------
# PUBLIC CITIZEN HOME PAGE
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# ADMIN LOGIN
# ---------------------------------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():

    if session.get("is_admin"):
        return redirect(url_for("admin_dashboard"))

    error = None
    token = _csrf_token()

    if request.method == "POST":

        if not _valid_csrf():

            error = "Invalid security token. Please refresh and try again."

        else:

            username = request.form.get("username", "")
            password = request.form.get("password", "")

            username_ok = hmac.compare_digest(
                username, ADMIN_USERNAME
            )

            password_ok = hmac.compare_digest(
                password, ADMIN_PASSWORD
            )

            if username_ok and password_ok:

                session.clear()
                session["is_admin"] = True
                session.permanent = True
                _csrf_token()

                return redirect(url_for("admin_dashboard"))

            error = "Invalid username or password."

    return render_template(
        "admin_login.html",
        error=error,
        csrf_token=token
    )


# ---------------------------------------------------------------------------
# ADMIN DASHBOARD
# ---------------------------------------------------------------------------

@app.route("/admin")
@admin_required
def admin_dashboard():

    return render_template(
        "admin.html",
        csrf_token=_csrf_token()
    )


# ---------------------------------------------------------------------------
# ADMIN LOGOUT
# ---------------------------------------------------------------------------

@app.route("/admin/logout", methods=["POST"])
@admin_required
def admin_logout():

    if not _valid_csrf():
        return jsonify({
            "error": "Invalid security token."
        }), 403

    session.clear()

    return redirect(url_for("admin_login"))


# ---------------------------------------------------------------------------
# PRIVATE PHOTO ACCESS
# ---------------------------------------------------------------------------

@app.route("/admin/photo/<path:filename>")
@admin_required
def uploaded_file(filename):
    file_path = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.isfile(file_path):
        return send_from_directory(
            UPLOAD_FOLDER,
            filename
        )

    fallback_dir = os.path.join(BASE_DIR, "private_uploads")
    if os.path.isfile(os.path.join(fallback_dir, filename)):
        return send_from_directory(
            fallback_dir,
            filename
        )

    return jsonify({
        "error": "Photo not found or expired from ephemeral storage."
    }), 404


# ---------------------------------------------------------------------------
# ADMIN DASHBOARD SUMMARY API
# ---------------------------------------------------------------------------

@app.route("/api/summary")
@admin_required
def api_summary():

    return jsonify(
        analysis.summary(_assets())
    )


# ---------------------------------------------------------------------------
# ADMIN-ONLY BBMP SYNCHRONIZATION
# ---------------------------------------------------------------------------

@app.route("/api/sync-bbmp", methods=["POST"])
@admin_required
def api_sync_bbmp():

    if not _valid_csrf():
        return jsonify({
            "error": "Invalid security token."
        }), 403

    try:
        app.logger.info("Starting BBMP data synchronization.")

        result = bbmp_sync.sync_workorders()

        return jsonify({
            "message": "BBMP data synchronization completed.",
            **result
        })

    except Exception:
        app.logger.exception("BBMP synchronization failed")

        return jsonify({
            "error": "BBMP synchronization failed. Check server logs."
        }), 500


# ---------------------------------------------------------------------------
# ADMIN-ONLY ASSETS API
# ---------------------------------------------------------------------------

@app.route("/api/assets")
@admin_required
def api_assets():

    cat = request.args.get("category")

    assets = _assets()

    if cat:
        assets = [
            a for a in assets
            if a["category"] == cat
        ]

    return jsonify([
        analysis.public_asset(a)
        for a in assets
    ])


# ---------------------------------------------------------------------------
# ADMIN-ONLY INDIVIDUAL ASSET HISTORY
# ---------------------------------------------------------------------------

@app.route("/api/asset/<asset_id>")
@admin_required
def api_asset(asset_id):
    for a in _assets():
        if a["id"] == asset_id:
            payload = analysis.public_asset(
                a,
                with_timeline=True
            )

            payload["bbmp_work_orders"] = _find_bbmp_work_orders(a)

            return jsonify(payload)

    return jsonify({
        "error": "Asset not found."
    }), 404


# ---------------------------------------------------------------------------
# ADMIN-ONLY CITIZEN REPORTS API
# ---------------------------------------------------------------------------

@app.route("/api/reports")
@admin_required
def api_reports():
    if not os.path.exists(DB):
        return jsonify([])

    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row

    try:
        table_exists = con.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            AND name = 'complaints'
        """).fetchone()

        if not table_exists:
            return jsonify([])

        rows = con.execute("""
            SELECT
                id,
                reference_id,
                category,
                text,
                lat,
                lon,
                reported_on,
                severity,
                status,
                photo_path
            FROM complaints
            ORDER BY id DESC
        """).fetchall()

        reports = []

        for row in rows:
            reports.append({
                "id": row["id"],
                "reference_id": row["reference_id"],
                "category": row["category"],
                "text": row["text"],
                "lat": row["lat"],
                "lon": row["lon"],
                "reported_on": row["reported_on"],
                "severity": row["severity"],
                "status": row["status"],
                "photo_path": row["photo_path"]
            })

        return jsonify(reports)

    finally:
        con.close()


# ---------------------------------------------------------------------------
# PUBLIC CITIZEN COMPLAINT SUBMISSION
# ---------------------------------------------------------------------------

@app.route("/api/complaint", methods=["POST"])
def api_complaint():

    content_type = request.content_type or ""

    if (
        "multipart/form-data" in content_type
        or "application/x-www-form-urlencoded" in content_type
    ):
        data = request.form
    else:
        data = request.get_json(silent=True) or {}

    text = (data.get("text") or "").strip()
    category = _normalize_category(data.get("category"))

    try:
        lat = float(data["lat"])
        lon = float(data["lon"])
        severity = int(data.get("severity", 2))

    except (KeyError, ValueError, TypeError):
        return jsonify({
            "error": "Valid location and severity are required."
        }), 400

    if not text:
        return jsonify({
            "error": "Please describe the problem."
        }), 400

    if len(text) > 2000:
        return jsonify({
            "error": "Description is too long."
        }), 400

    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify({
            "error": "Invalid location coordinates."
        }), 400

    severity = max(1, min(5, severity))

    # -----------------------------------------------------------------------
    # SAVE OPTIONAL PHOTO PRIVATELY
    # -----------------------------------------------------------------------

    photo_path = None
    photo = request.files.get("photo")

    if photo and photo.filename:

        if not _allowed_file(photo.filename):
            return jsonify({
                "error": "Only JPG, JPEG and PNG images are allowed."
            }), 400

        photo.stream.seek(0, 2)
        file_size = photo.stream.tell()
        photo.stream.seek(0)

        if file_size > MAX_UPLOAD_BYTES:
            return jsonify({
                "error": "Image must be 5 MB or smaller."
            }), 400

        extension = photo.filename.rsplit(".", 1)[1].lower()
        safe_name = f"{uuid.uuid4().hex}.{extension}"

        save_path = os.path.join(
            UPLOAD_FOLDER,
            safe_name
        )

        try:
            photo.save(save_path)
            photo_path = f"/admin/photo/{safe_name}"

        except Exception:
            app.logger.exception("Photo upload failed")

            return jsonify({
                "error": "Photo could not be saved."
            }), 500

    # -----------------------------------------------------------------------
    # MATCH INTERNALLY WITH EXISTING COMPLAINT CLUSTERS
    # -----------------------------------------------------------------------

    try:
        before = _assets()

        analysis.match_complaint(
            text,
            category,
            lat,
            lon,
            before
        )

    except Exception:
        app.logger.exception("Complaint matching failed")

        if photo_path:
            try:
                os.remove(
                    os.path.join(
                        UPLOAD_FOLDER,
                        os.path.basename(photo_path)
                    )
                )
            except OSError:
                pass

        return jsonify({
            "error": "Complaint could not be processed. Please try again."
        }), 500

    # -----------------------------------------------------------------------
    # SAVE COMPLAINT AND GENERATE REFERENCE ID
    # -----------------------------------------------------------------------

    con = sqlite3.connect(DB)

    try:
        cursor = con.execute(
            """
            INSERT INTO complaints (
                category,
                text,
                lat,
                lon,
                reported_on,
                severity,
                status,
                photo_path
            )
            VALUES (?, ?, ?, ?, ?, ?, 'Open', ?)
            """,
            (
                category,
                text,
                lat,
                lon,
                date.today().isoformat(),
                severity,
                photo_path
            )
        )

        complaint_id = cursor.lastrowid
        reference_id = f"CM-{complaint_id:06d}"

        con.execute(
            """
            UPDATE complaints
            SET reference_id = ?
            WHERE id = ?
            """,
            (reference_id, complaint_id)
        )

        con.commit()

    except Exception:
        app.logger.exception("Complaint database insert failed")

        if photo_path:
            try:
                os.remove(
                    os.path.join(
                        UPLOAD_FOLDER,
                        os.path.basename(photo_path)
                    )
                )
            except OSError:
                pass

        return jsonify({
            "error": "Complaint could not be saved. Please try again."
        }), 500

    finally:
        con.close()

    return jsonify({
        "message": "Your complaint has been submitted successfully.",
        "success": True,
        "reference_id": reference_id
    }), 201


# ---------------------------------------------------------------------------
# ADMIN-ONLY DEMO RESET
# PROTECT IMPORTED BBMP RECORDS
# ---------------------------------------------------------------------------

@app.route("/api/reset", methods=["POST"])
@admin_required
def api_reset():

    if not _valid_csrf():
        return jsonify({
            "error": "Invalid security token."
        }), 403

    try:
        bbmp_count = _bbmp_workorder_count()

    except sqlite3.Error:
        app.logger.exception(
            "Could not verify BBMP database records"
        )

        return jsonify({
            "error": (
                "Reset blocked because BBMP database "
                "protection could not be verified."
            )
        }), 500

    if bbmp_count > 0:
        return jsonify({
            "error": (
                f"Demo reset disabled because {bbmp_count} "
                "BBMP work orders are stored. "
                "Your imported data is protected."
            )
        }), 409

    try:
        n = generate_data.generate(db_path=DB)

        _migrate_db()

        if os.path.exists(UPLOAD_FOLDER):
            for filename in os.listdir(UPLOAD_FOLDER):
                path = os.path.join(UPLOAD_FOLDER, filename)

                if os.path.isfile(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass

        return jsonify({
            "message": f"Reset with {n} simulated complaints."
        })

    except Exception:
        app.logger.exception("Demo reset failed")

        return jsonify({
            "error": "Demo reset failed. Check server logs."
        }), 500


# ---------------------------------------------------------------------------
# FLASK APPLICATION
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    app.run(
        debug=os.environ.get("FLASK_DEBUG") == "1",
        port=5000
    )