"""Run the offline smoke demo with ``python -m idx_evidence_lab``."""

from pprint import pprint

from .demo import smoke


if __name__ == "__main__":
    pprint(smoke())
