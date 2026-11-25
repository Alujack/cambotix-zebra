"""Structured outputs the local model must return. Anything that fails validation is discarded, never repaired."""
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

COMMANDS = ('open', 'price', 'record', 'signals', 'news', 'cost', 'status')


class Route(BaseModel):
    """How one Telegram question is handled: an exact command, a free local answer, or paid deep analysis."""
    model_config = ConfigDict(extra='forbid')
    route: Literal['COMMAND', 'SIMPLE', 'DEEP']
    command: Literal['open', 'price', 'record', 'signals', 'news', 'cost', 'status', 'none'] = 'none'
    argument: str = Field(default='', max_length=20)
    confidence: int = Field(ge=0, le=100)


class TradeNote(BaseModel):
    model_config = ConfigDict(extra='forbid')
    note: str = Field(min_length=10, max_length=280)

    @field_validator('note')
    @classmethod
    def plain(cls, value):
        if '\n\n' in value or value.count('\n') > 2:
            raise ValueError('a trade note is one or two lines')
        return value.strip()


class PlanNote(BaseModel):
    model_config = ConfigDict(extra='forbid')
    note: str = Field(min_length=40, max_length=480)

    @field_validator('note')
    @classmethod
    def plain(cls, value):
        if '\n' in value.strip():
            raise ValueError('a plan note is one short paragraph')
        return value.strip()


NUMBER = re.compile(r'\d+(?:\.\d+)?')


def unsupported_numbers(text: str, facts: str) -> list[str]:
    """Numbers with 3+ significant digits in `text` that do not appear in `facts`: invented prices or levels."""
    known = {round(float(item), 2) for item in NUMBER.findall(facts)}
    return [item for item in NUMBER.findall(text)
            if len(item.replace('.', '').lstrip('0')) >= 3 and round(float(item), 2) not in known]
