from rentwatch.routing import _path_distance_m, route_key


def test_path_distance_uses_geometry_points():
    distance = _path_distance_m("[[51.5,-0.1],[51.5,-0.09]]")

    assert distance is not None
    assert 690 < distance < 710


def test_route_key_contains_algorithm_version():
    key = route_key("tfl", "cycling", 51.5, -0.1, 51.6, -0.2)

    assert key.startswith("tfl:geometry-v1:cycling:default:")
