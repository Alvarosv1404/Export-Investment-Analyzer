from exportanalysis.pipeline.market import moving_average_projection


def test_moving_average_projection_forecasts_two_years_from_last_three_values():
    result = moving_average_projection(
        [
            {"year": 2020, "fob_usd": 10.0},
            {"year": 2021, "fob_usd": 20.0},
            {"year": 2022, "fob_usd": 30.0},
            {"year": 2023, "fob_usd": 60.0},
            {"year": 2024, "fob_usd": 90.0},
        ]
    )

    assert result["available"] is True
    assert result["window_years"] == [2022, 2023, 2024]
    assert result["forecast_years"] == [2025, 2026]
    assert [row["value"] for row in result["forecast"]] == [60.0, 60.0]


def test_moving_average_projection_requires_consecutive_recent_years():
    result = moving_average_projection(
        [
            {"year": 2020, "fob_usd": 10.0},
            {"year": 2021, "fob_usd": 20.0},
            {"year": 2023, "fob_usd": 30.0},
            {"year": 2024, "fob_usd": 40.0},
        ]
    )

    assert result["available"] is False
