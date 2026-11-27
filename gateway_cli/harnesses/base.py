"""Small harness discovery contract; no shell execution is required."""
from dataclasses import dataclass
import shutil

@dataclass(frozen=True)
class Harness:
    name: str
    display_name: str
    executable: str

    def detect(self):
        return shutil.which(self.executable)
