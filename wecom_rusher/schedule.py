from dataclasses import dataclass
from datetime import time


@dataclass(frozen=True)
class PollSchedule:
    normal_interval: float
    rush_interval: float
    rush_start: time
    rush_end: time

    def interval_at(self, now: time) -> float:
        return self.rush_interval if self.rush_start <= now < self.rush_end else self.normal_interval
