"""Inner loop: password hashing and JWT handling as pure units."""

from datetime import timedelta

import pytest

from app.core.security import (
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_password_does_not_contain_the_plaintext(self) -> None:
        hashed = hash_password("correct-horse-battery")

        assert "correct-horse-battery" not in hashed

    def test_hash_password_is_salted_so_two_hashes_differ(self) -> None:
        first = hash_password("correct-horse-battery")
        second = hash_password("correct-horse-battery")

        assert first != second

    def test_verify_password_accepts_the_right_password(self) -> None:
        hashed = hash_password("correct-horse-battery")

        assert verify_password("correct-horse-battery", hashed) is True

    def test_verify_password_rejects_the_wrong_password(self) -> None:
        hashed = hash_password("correct-horse-battery")

        assert verify_password("guessing-wildly", hashed) is False

    def test_verify_password_rejects_a_malformed_hash_instead_of_raising(self) -> None:
        assert verify_password("correct-horse-battery", "not-a-bcrypt-hash") is False

    @pytest.mark.parametrize("length", [71, 72, 73, 200])
    def test_hash_password_handles_passwords_past_the_bcrypt_byte_limit(self, length: int) -> None:
        """bcrypt truncates at 72 bytes; pre-hashing must keep long passwords distinct."""
        password = "a" * length
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True
        assert verify_password(password + "b", hashed) is False


class TestAccessTokens:
    def test_create_access_token_round_trips_the_subject(self) -> None:
        token = create_access_token(subject="ana@example.com")

        assert decode_access_token(token).subject == "ana@example.com"

    def test_decode_access_token_rejects_an_expired_token(self) -> None:
        token = create_access_token(subject="ana@example.com", expires_delta=timedelta(minutes=-1))

        with pytest.raises(InvalidTokenError):
            decode_access_token(token)

    def test_decode_access_token_rejects_a_tampered_signature(self) -> None:
        token = create_access_token(subject="ana@example.com")
        tampered = token[:-4] + "AAAA"

        with pytest.raises(InvalidTokenError):
            decode_access_token(tampered)

    def test_decode_access_token_rejects_a_token_signed_with_another_secret(self) -> None:
        import jwt

        foreign = jwt.encode({"sub": "ana@example.com", "exp": 9999999999}, "other", "HS256")

        with pytest.raises(InvalidTokenError):
            decode_access_token(foreign)

    def test_decode_access_token_rejects_a_token_with_no_subject(self) -> None:
        import jwt

        from app.core.config import get_settings

        settings = get_settings()
        no_subject = jwt.encode(
            {"exp": 9999999999}, settings.jwt_secret, algorithm=settings.jwt_algorithm
        )

        with pytest.raises(InvalidTokenError):
            decode_access_token(no_subject)

    def test_decode_access_token_rejects_an_empty_subject(self) -> None:
        import jwt

        from app.core.config import get_settings

        settings = get_settings()
        empty_subject = jwt.encode(
            {"sub": "", "exp": 9999999999}, settings.jwt_secret, algorithm=settings.jwt_algorithm
        )

        with pytest.raises(InvalidTokenError):
            decode_access_token(empty_subject)

    def test_decode_access_token_rejects_gibberish(self) -> None:
        with pytest.raises(InvalidTokenError):
            decode_access_token("not.a.token")
