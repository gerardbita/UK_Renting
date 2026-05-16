from rentwatch.rightmove_location import LocationSuggestion


def test_location_identifier_combines_type_and_id():
    suggestion = LocationSuggestion(id="918640", type="POSTCODE", display_name="W2 1SJ")

    assert suggestion.location_identifier == "POSTCODE^918640"
