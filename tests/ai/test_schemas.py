import pytest
from pydantic import ValidationError

from app.ai.schemas import Route, TradeNote, unsupported_numbers


def test_trade_note_is_short():
    assert TradeNote(note='Swept the range low, then reached TP1.').note.startswith('Swept')
    for bad in ['too short', 'x' * 281, 'line one\n\nline two', 'a\nb\nc\nd is too many lines']:
        with pytest.raises(ValidationError):
            TradeNote(note=bad)


def test_route_refuses_unknown_fields_and_routes():
    with pytest.raises(ValidationError):
        Route.model_validate({'route': 'EXECUTE', 'confidence': 90})
    with pytest.raises(ValidationError):
        Route.model_validate({'route': 'SIMPLE', 'confidence': 90, 'tool': 'sql'})


def test_invented_numbers_are_detected():
    facts = '{"entry":3506.0,"stop":3493.4,"targets":[3540.0],"r_tp1":2.7}'
    assert unsupported_numbers('Hit TP1 at 3540 after holding 3506.', facts) == []
    assert unsupported_numbers('Reversed from 3521.5 to the stop.', facts) == ['3521.5']
    # Short numbers (R values, counts, hours) are not treated as price levels.
    assert unsupported_numbers('Won 2.7R in 3 candles.', facts) == []
