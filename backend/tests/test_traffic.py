from homenas.db import Database


def test_mihomo_traffic_summary_sorts_upload_and_download(tmp_path):
    db = Database(tmp_path / "homenas.db")
    try:
        db.add_mihomo_traffic_samples([
            {"ts": "2026-11-26T00:00:01+00:00", "domain": "small.example", "upload_bytes": 30, "download_bytes": 500},
            {"ts": "2026-11-26T00:00:02+00:00", "domain": "large.example", "upload_bytes": 900, "download_bytes": 100},
            {"ts": "2026-11-26T00:00:03+00:00", "domain": "small.example", "upload_bytes": 20, "download_bytes": 700},
        ])
        summary = db.mihomo_traffic_summary(24 * 30)
        assert summary["total_upload_bytes"] == 950
        assert summary["total_download_bytes"] == 1300
        assert summary["download"][0]["domain"] == "small.example"
        assert summary["upload"][0]["domain"] == "large.example"
        assert summary["domain_count"] == 2
    finally:
        db.close()
