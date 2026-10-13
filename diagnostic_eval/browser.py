"""Observe failures around the unchanged interaction implementation."""
from fresh_eval.browser import EvaluationBrowser
from .diagnostics import Writer, action_metadata, probe_control


class DiagnosticBrowser(EvaluationBrowser):
    def interact(self, decision, request):
        if not hasattr(self, "diagnostic_writer"):
            self.diagnostic_writer = Writer(self.store.run_dir)
        metadata = action_metadata(self, decision)
        self.diagnostic_writer.emit("before_interact", metadata)
        try:
            return super().interact(decision, request)
        except BaseException as error:
            probe = probe_control(self, metadata["control_index"]) if isinstance(error, Exception) else None
            self.diagnostic_writer.emit("interaction_error", metadata, error=error, probe=probe)
            raise
