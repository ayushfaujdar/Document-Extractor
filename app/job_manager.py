import threading
import uuid
from concurrent.futures import ThreadPoolExecutor


# Number of documents that can be processed simultaneously.
# Start small on your Mac.
MAX_WORKERS = 2

executor = ThreadPoolExecutor(
    max_workers=MAX_WORKERS
)

_jobs = {}

_lock = threading.Lock()


def create_job():
    job_id = uuid.uuid4().hex

    with _lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "result": None,
            "error": None
        }

    return job_id


def update_job(job_id, **updates):

    with _lock:

        if job_id not in _jobs:
            return

        _jobs[job_id].update(updates)


def get_job(job_id):

    with _lock:

        job = _jobs.get(job_id)

        if job is None:
            return None

        # Return a copy so another thread cannot modify
        # the object while Flask is reading it.
        return dict(job)


def submit_job(job_id, function, *args, **kwargs):

    update_job(
        job_id,
        status="queued"
    )

    executor.submit(
        _run_job,
        job_id,
        function,
        *args,
        **kwargs
    )


def _run_job(job_id, function, *args, **kwargs):

    update_job(
        job_id,
        status="processing"
    )

    try:

        result = function(
            *args,
            **kwargs
        )

        update_job(
            job_id,
            status="completed",
            result=result
        )

    except Exception as e:

        update_job(
            job_id,
            status="failed",
            error=str(e)
        )