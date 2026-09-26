from app.security import hash_password, new_session_token, token_digest, verify_password


def test_password_hash_is_argon2id_and_verifies():
    h = hash_password("correct-horse-42")
    assert h.startswith("$argon2id$")
    assert "correct-horse-42" not in h
    assert verify_password(h, "correct-horse-42")
    assert not verify_password(h, "wrong-password-42")


def test_verify_tolerates_garbage_hash():
    assert not verify_password("not-a-hash", "whatever-123")


def test_session_tokens_are_random_and_only_digest_is_stored():
    a, b = new_session_token(), new_session_token()
    assert a != b and len(a) >= 43  # 32 байта в base64url
    assert len(token_digest(a)) == 32
    assert token_digest(a) != token_digest(b)
