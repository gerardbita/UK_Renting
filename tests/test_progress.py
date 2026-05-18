from unittest.mock import patch

from rentwatch.progress import fit_message_to_terminal


def test_progress_message_is_trimmed_to_terminal_width():
    with patch("rentwatch.progress.get_terminal_size") as get_size:
        get_size.return_value.columns = 40

        message = fit_message_to_terminal("Routes [###---] 10/100 listings | long address here")

    assert len(message) == 40
    assert message.endswith("...")
