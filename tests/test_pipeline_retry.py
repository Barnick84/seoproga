import pytest

from utils.retry import RetryExhausted, with_retry


def test_step_retry_success_on_second():
    """Simulate a step that fails once then succeeds."""
    call_count = 0

    @with_retry(max_retries=2, base_delay=0.01)
    def step():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ConnectionError("XMLRiver timeout")
        return {"success": True, "data": "ok"}

    result = step()
    assert result["success"] is True
    assert call_count == 2


def test_step_retry_exhausted_on_persistent_failure():
    call_count = 0

    @with_retry(max_retries=1, base_delay=0.01)
    def step():
        nonlocal call_count
        call_count += 1
        raise ValueError("disk full")

    with pytest.raises(RetryExhausted):
        step()
    assert call_count == 2


def test_pipeline_skip_completed_steps():
    """Simulate checking completed_steps in payload."""
    payload = {"completed_steps": [2, 3]}
    completed_steps = payload.get("completed_steps", [])

    executed_steps = []
    should_run = {1, 2, 3, 4}
    for step_num in sorted(should_run):
        if step_num in completed_steps:
            continue
        executed_steps.append(step_num)

    assert executed_steps == [1, 4]


def test_pipeline_mark_complete():
    completed_steps = []
    payload = {}

    def mark_complete(step_num: int):
        completed_steps.append(step_num)
        payload["completed_steps"] = list(completed_steps)

    mark_complete(2)
    mark_complete(5)

    assert payload["completed_steps"] == [2, 5]
    assert 1 not in payload["completed_steps"]


def test_pipeline_collect_step_errors():
    step_errors: dict[int, str] = {}
    errors_to_simulate = {2: "connection", 4: "timeout"}

    for step_num in [1, 2, 3, 4, 5]:
        if step_num in errors_to_simulate:
            step_errors[step_num] = errors_to_simulate[step_num]

    assert len(step_errors) == 2
    assert step_errors[2] == "connection"
