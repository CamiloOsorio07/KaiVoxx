from dataclasses import dataclass
from typing import Any

@dataclass
class Song:
    url: str
    title: str
    requester_name: str
    channel: Any
    source: str = "YouTube"
