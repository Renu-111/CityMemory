"""Automated tests for Phase 1 – Photo Evidence Upload."""
import os
import struct
import zlib
import requests

BASE = "http://127.0.0.1:5000"
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "static", "uploads")


def tiny_png():
    """Build a minimal valid 1x1 RGB PNG."""
    def chunk(tag, data):
        crc = zlib.crc32(tag + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", crc)

    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = b"\x00\xff\x00\x00"
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return b"\x89PNG\r\n\x1a\n" + ihdr + idat + iend


PNG = tiny_png()
BASE_DATA = {
    "text": "Big pothole near Silk Board again",
    "category": "pothole",
    "severity": "3",
    "lat": "12.9172",
    "lon": "77.6228",
}


def test_existing_data_intact():
    r = requests.get(BASE + "/api/summary")
    s = r.json()
    print(f"[T1] total_complaints={s['total_complaints']}")
    assert r.status_code == 200
    assert s["total_complaints"] >= 235, f"Expected >=235, got {s['total_complaints']}"
    print("PASS: existing records preserved\n")


def test_submit_without_photo():
    r = requests.post(BASE + "/api/complaint", data={
        "text": "Road cracked near Hebbal Flyover test",
        "category": "pothole",
        "severity": "2",
        "lat": "13.0358",
        "lon": "77.5970",
    })
    d = r.json()
    print(f"[T2] HTTP {r.status_code} is_repeat={d.get('is_repeat')} photo_url={d.get('photo_url')}")
    assert r.status_code == 200, d
    assert d["photo_url"] is None
    print("PASS: null photo_url when no file attached\n")


def test_submit_with_valid_png():
    files = {"photo": ("complaint.png", PNG, "image/png")}
    r = requests.post(BASE + "/api/complaint", data=BASE_DATA, files=files)
    d = r.json()
    print(f"[T3] HTTP {r.status_code} photo_url={d.get('photo_url')}")
    assert r.status_code == 200, d
    assert d["photo_url"] is not None
    assert d["photo_url"].startswith("/static/uploads/")
    fname = d["photo_url"].split("/")[-1]
    fpath = os.path.join(UPLOAD_DIR, fname)
    assert os.path.exists(fpath), f"File not on disk: {fpath}"
    print(f"PASS: photo saved as {fname}\n")
    return d


def test_timeline_has_photo_path(asset_id):
    r = requests.get(BASE + "/api/asset/" + asset_id)
    a = r.json()
    assert "timeline" in a, "No timeline in response"
    has_photo = any(e.get("photo_path") for e in a["timeline"])
    print(f"[T4] asset={asset_id} entries={len(a['timeline'])} any_with_photo={has_photo}")
    assert has_photo
    print("PASS: photo_path present in timeline\n")


def test_reject_wrong_type():
    bad = {"photo": ("evil.gif", b"GIF89a\x01\x00\x00\x00\x00", "image/gif")}
    r = requests.post(BASE + "/api/complaint", data=BASE_DATA, files=bad)
    d = r.json()
    print(f"[T5] HTTP {r.status_code} error={d.get('error')}")
    assert r.status_code == 400
    assert "JPG" in d["error"] or "PNG" in d["error"]
    print("PASS: wrong file type rejected\n")


def test_reject_oversized():
    big = b"A" * (5 * 1024 * 1024 + 1)
    big_files = {"photo": ("huge.jpg", big, "image/jpeg")}
    r = requests.post(BASE + "/api/complaint", data=BASE_DATA, files=big_files)
    d = r.json()
    print(f"[T6] HTTP {r.status_code} error={d.get('error')}")
    assert r.status_code == 400
    assert "5 MB" in d["error"]
    print("PASS: oversized file rejected\n")


def test_repeat_detection_unaffected():
    repeat_data = {
        "text": "Same pothole near Silk Board cracked again after patch",
        "category": "pothole",
        "severity": "4",
        "lat": "12.9172",
        "lon": "77.6228",
    }
    r1 = requests.post(BASE + "/api/complaint", data=repeat_data)
    d1 = r1.json()
    files = {"photo": ("repeat.png", PNG, "image/png")}
    r2 = requests.post(BASE + "/api/complaint", data=repeat_data, files=files)
    d2 = r2.json()
    print(f"[T7] no_photo: is_repeat={d1.get('is_repeat')} conf={d1.get('match_confidence')}")
    print(f"[T7] with_photo: is_repeat={d2.get('is_repeat')} conf={d2.get('match_confidence')}")
    assert d1["is_repeat"] == d2["is_repeat"], "Repeat detection changed with photo!"
    print("PASS: repeat detection identical with and without photo\n")


def test_reset_no_error():
    r = requests.post(BASE + "/api/reset")
    d = r.json()
    print(f"[T8] HTTP {r.status_code} message={d.get('message')}")
    assert r.status_code == 200
    assert "simulated" in d["message"].lower()
    print("PASS: reset succeeds even with uploaded files\n")


if __name__ == "__main__":
    test_existing_data_intact()
    test_submit_without_photo()
    result = test_submit_with_valid_png()
    test_timeline_has_photo_path(result["asset_id"])
    test_reject_wrong_type()
    test_reject_oversized()
    test_repeat_detection_unaffected()
    test_reset_no_error()
    print("=" * 40)
    print("ALL TESTS PASSED")
    print("=" * 40)
