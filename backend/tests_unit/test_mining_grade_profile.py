from app.dispatch.mining_grade_profile import DirectionalGrades, SurveyPoint, surveyed_grades


def test_directional_maxima_not_average() -> None:
    points = [SurveyPoint(0, 1000), SurveyPoint(10000, 2000), SurveyPoint(20000, 1400)]
    assert surveyed_grades(points) == DirectionalGrades(100, 60)


def test_reverse_direction_swaps_grades() -> None:
    points = [SurveyPoint(0, 1400), SurveyPoint(10000, 2000), SurveyPoint(20000, 1000)]
    assert surveyed_grades(points) == DirectionalGrades(60, 100)


def test_rounds_up_and_supports_flat_roads() -> None:
    assert surveyed_grades([SurveyPoint(0, 0), SurveyPoint(3000, 1)]) == DirectionalGrades(1, 0)
    assert surveyed_grades([SurveyPoint(0, -10), SurveyPoint(1000, -10)]) == DirectionalGrades(0, 0)


def test_invalid_profiles_are_rejected() -> None:
    assert surveyed_grades([]) is None
    assert surveyed_grades([SurveyPoint(0, 0)]) is None
    assert surveyed_grades([SurveyPoint(1, 0), SurveyPoint(2, 0)]) is None
    assert surveyed_grades([SurveyPoint(0, 0), SurveyPoint(0, 1)]) is None
    assert surveyed_grades([SurveyPoint(0, 0), SurveyPoint(2, 1), SurveyPoint(1, 0)]) is None
    assert surveyed_grades([SurveyPoint(i, 0) for i in range(10001)]) is None
