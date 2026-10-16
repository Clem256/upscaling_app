"""
Cancellation support shared by the UI thread and the worker thread.
"""


class Cancelled(Exception):
    """Raised from deep inside the processing code when the user cancels."""


class Control:
    """Cancellation handle shared between the UI thread and the worker thread."""

    def __init__(self):
        self.proc = None         # engine subprocess currently running, if any
        self.cancelled = False   # checked by long-running loops

    def cancel(self):
        """Flag the job as cancelled and stop the engine process if it is running."""
        self.cancelled = True
        p = self.proc
        if p is not None and p.poll() is None:
            p.terminate()
