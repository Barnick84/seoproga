import pytest

from utils.retry import RetryExhausted, with_retry


def test_retry_success_on_first_attempt():
    call_count = 0

    @with_retry(max_retries=2, base_delay=0.01)
    def do_work():
        nonlocal call_count
        call_count += 1
        return "ok"

    result = do_work()
    assert result == "ok"
    assert call_count == 1


def test_retry_success_on_second_attempt():
    call_count = 0

    @with_retry(max_retries=2, base_delay=0.01)
    def do_work():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("temporary error")
        return "ok"

    result = do_work()
    assert result == "ok"
    assert call_count == 2


def test_retry_exhausted():
    call_count = 0

    @with_retry(max_retries=2, base_delay=0.01)
    def do_work():
        nonlocal call_count
        call_count += 1
        raise ValueError("persistent error")

    with pytest.raises(RetryExhausted):
        do_work()
    assert call_count == 3  # 1 initial + 2 retries


def test_retry_specific_exception():
    class CustomError(Exception):
        pass

    call_count = 0

    @with_retry(max_retries=1, base_delay=0.01, exceptions=(CustomError,))
    def do_work():
        nonlocal call_count
        call_count += 1
        raise ValueError("not custom")

    with pytest.raises(ValueError):
        do_work()
    assert call_count == 1  # No retry on unmatched exception


def test_retry_on_retry_callback():
    retries = []

    @with_retry(
        max_retries=2,
        base_delay=0.01,
        on_retry=lambda e, a: retries.append((str(e), a)),
    )
    def do_work():
        raise ValueError("fail")

    with pytest.raises(RetryExhausted):
        do_work()
    assert len(retries) == 2
    assert "fail" in retries[0][0]
    assert retries[0][1] == 1
    assert retries[1][1] == 2
