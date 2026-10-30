"""The 0-100 progress scale streamed while a repository is ingested.

The API stream reports download and parsing, and the graph writer reports the
database passes. Both place their updates on this one scale, so the stream only
moves forward and its last record is ``COMPLETE``, which the dashboard treats as
the final result.
"""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProgressSpan:
    """A stage that advances from ``start`` to ``end`` as its items complete."""

    start: int
    end: int

    def at(self, completed: int, total: int) -> int:
        """Return the progress after ``completed`` of ``total`` items."""

        if total <= 0:
            return self.end
        return self.start + (self.end - self.start) * completed // total


DOWNLOAD_STARTED = 10
DOWNLOADED = 20
PARSING = ProgressSpan(DOWNLOADED, 80)
DATABASE_STARTED = 85
FILES_STARTED = 86
FUNCTIONS = ProgressSpan(90, 93)
DEPENDENCIES = ProgressSpan(94, 96)
COMMUNITY_DETECTION_STARTED = 97
COMMUNITY_LABELING_STARTED = 98
COMMITTING = 99
COMPLETE = 100
