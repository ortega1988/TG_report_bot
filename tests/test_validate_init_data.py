import hashlib
import hmac
import time
from unittest.mock import patch
from urllib.parse import urlencode

from webapp.server import validate_init_data, INIT_DATA_MAX_AGE


BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"


def _build_init_data(params: dict, token: str = BOT_TOKEN) -> str:
    """Build a valid init_data string with correct HMAC hash."""
    data_check_arr = sorted([f"{k}={v}" for k, v in params.items()])
    data_check_string = "\n".join(data_check_arr)

    secret_key = hmac.new(
        b"WebAppData", token.encode(), hashlib.sha256
    ).digest()

    calculated_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    params["hash"] = calculated_hash
    return urlencode(params)


class TestValidateInitData:
    def test_valid_data(self):
        params = {
            "auth_date": str(int(time.time())),
            "user": '{"id":123,"first_name":"Test"}',
            "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        }
        init_data = _build_init_data(params)
        result = validate_init_data(init_data, BOT_TOKEN)

        assert result is not None
        assert result["user"]["id"] == 123

    def test_invalid_hash(self):
        params = {
            "auth_date": str(int(time.time())),
            "user": '{"id":123}',
        }
        init_data = _build_init_data(params)
        # Tamper with the data
        init_data = init_data.replace("auth_date", "auth_datx")
        result = validate_init_data(init_data, BOT_TOKEN)

        assert result is None

    def test_missing_hash(self):
        init_data = "auth_date=12345&user=%7B%22id%22%3A1%7D"
        result = validate_init_data(init_data, BOT_TOKEN)
        assert result is None

    def test_wrong_token(self):
        params = {
            "auth_date": str(int(time.time())),
            "user": '{"id":123}',
        }
        init_data = _build_init_data(params, token=BOT_TOKEN)
        result = validate_init_data(init_data, "wrong:token")

        assert result is None

    def test_expired_auth_date(self):
        old_time = int(time.time()) - INIT_DATA_MAX_AGE - 100
        params = {
            "auth_date": str(old_time),
            "user": '{"id":123}',
        }
        init_data = _build_init_data(params)
        result = validate_init_data(init_data, BOT_TOKEN)

        assert result is None

    def test_recent_auth_date(self):
        params = {
            "auth_date": str(int(time.time()) - 60),
            "user": '{"id":123}',
        }
        init_data = _build_init_data(params)
        result = validate_init_data(init_data, BOT_TOKEN)

        assert result is not None
