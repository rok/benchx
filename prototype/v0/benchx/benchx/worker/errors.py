"""Worker failures and the exit codes they map to (worker-prototype.md section 2)."""


class WorkerError(Exception):
    exit_code = 3


class OrderRejected(WorkerError):
    """The order cannot be run: invalid, unsupported, or target missing."""

    exit_code = 1


class PlanFailed(WorkerError):
    """The planned set could not be established, so nothing was planned."""

    exit_code = 2


class EmitFailed(WorkerError):
    """The worker produced a result that does not conform. A worker bug."""

    exit_code = 3
