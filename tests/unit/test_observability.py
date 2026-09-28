import logging

from app.observability import QueryStringRedactionFilter, monzo_error_details


def test_uvicorn_access_log_filter_removes_query_parameters():
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=(
            "127.0.0.1:1234",
            "GET",
            "/monzo-callback?code=sensitive-code&state=sensitive-state",
            "1.1",
            200,
        ),
        exc_info=None,
    )

    assert QueryStringRedactionFilter().filter(record)
    assert record.args[2] == "/monzo-callback"
    assert "sensitive-code" not in record.getMessage()
    assert "sensitive-state" not in record.getMessage()


def test_monzo_error_details_only_extracts_bounded_error_fields():
    response = type(
        "Response",
        (),
        {
            "json": lambda self: {
                "code": "bad_request",
                "message": "Invalid request\nTry again",
                "access_token": "must-not-be-logged",
            }
        },
    )()

    code, message = monzo_error_details(response)

    assert code == "bad_request"
    assert message == "Invalid request\\nTry again"
    assert "must-not-be-logged" not in f"{code} {message}"
