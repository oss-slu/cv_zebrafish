from core.pose.training.eta_estimate import estimate_remaining_seconds, format_duration


def test_format_duration_short():
    assert format_duration(0) == "0m 0s"
    assert format_duration(65) == "1m 5s"
    assert format_duration(3599) == "59m 59s"


def test_format_duration_hours():
    assert format_duration(3600) == "1h 0m"
    assert format_duration(3661) == "1h 1m 1s"


def test_estimate_remaining_seconds():
    assert estimate_remaining_seconds(100, 0, 50) is None
    assert estimate_remaining_seconds(100, 50, 50) is None
    assert estimate_remaining_seconds(100, 10, 50) == 400
