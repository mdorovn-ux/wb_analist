from wb_finance_analyst.services.update_checker import is_version_newer, update_info_from_payload


def test_version_comparison_understands_release_over_dev():
    assert is_version_newer("1.1.0", "1.1.0-dev")
    assert is_version_newer("1.1.1", "1.1.0")
    assert not is_version_newer("1.0.0", "1.1.0-dev")
    assert not is_version_newer("1.1.0-dev", "1.1.0")


def test_update_info_from_payload_marks_newer_version():
    info = update_info_from_payload(
        {
            "version": "1.2.0",
            "download_url": "https://example.test/app.zip",
            "notes_url": "https://example.test/notes",
        },
        current_version="1.1.0",
    )

    assert info.update_available
    assert info.latest_version == "1.2.0"
    assert info.download_url == "https://example.test/app.zip"

