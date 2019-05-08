from enum import Enum


class Status(Enum):
    Initialized = 1
    Building = 2
    Complete = 3
    Failed = 4
