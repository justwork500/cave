from datetime import timedelta

import pyotp
import pytest

from cave.auth.users import (
    LoginError,
    check_password,
    create_user,
    get_user,
    mfa_required,
    setup_totp,
    verify_second_factor,
)
from tests.conftest import T0

IP = "1.1.1.1"


def test_lockout_after_five_failures(db):
    create_user(db, "system", "sam", "correct horse", "household")
    for _ in range(5):
        with pytest.raises(LoginError):
            check_password(db, "sam", "nope", IP, T0)
    with pytest.raises(LoginError, match="Too many attempts"):
        check_password(db, "sam", "correct horse", IP, T0 + timedelta(minutes=14))
    assert check_password(db, "sam", "correct horse", IP, T0 + timedelta(minutes=16)).username == "sam"


def test_four_failures_then_success_resets_count(db):
    create_user(db, "system", "sam", "correct horse", "household")
    for _ in range(4):
        with pytest.raises(LoginError):
            check_password(db, "sam", "nope", IP, T0)
    check_password(db, "sam", "correct horse", IP, T0)
    with pytest.raises(LoginError, match="Wrong username"):
        check_password(db, "sam", "nope", IP, T0)


def test_unknown_user_same_message_and_logged(db):  # Review Focus 5
    with pytest.raises(LoginError) as e:
        check_password(db, "ghost", "x", IP, T0)
    assert e.value.message == "Wrong username or password."
    assert db.execute("SELECT count(*) FROM login_attempts WHERE username='ghost'").fetchone()[0] == 1


def test_disabled_user_cannot_sign_in(db):
    u = create_user(db, "system", "sam", "correct horse", "household")
    db.execute("UPDATE users SET enabled=0 WHERE id=?", (u.id,))
    with pytest.raises(LoginError, match="Wrong username"):
        check_password(db, "sam", "correct horse", IP, T0)


def test_admin_and_operator_need_mfa(db):
    assert mfa_required(create_user(db, "system", "a", "pw-aaaaaaaa", "admin"))
    assert mfa_required(create_user(db, "system", "o", "pw-aaaaaaaa", "operator"))
    assert not mfa_required(create_user(db, "system", "h", "pw-aaaaaaaa", "household"))


def test_household_with_totp_needs_mfa(db):
    u = create_user(db, "system", "h", "pw-aaaaaaaa", "household")
    setup_totp(db, u.id)
    assert mfa_required(get_user(db, u.id))


def test_totp_code_accepted(db):
    u = create_user(db, "system", "a", "pw-aaaaaaaa", "admin")
    uri, _ = setup_totp(db, u.id)
    assert verify_second_factor(db, u.id, pyotp.parse_uri(uri).now())
    assert not verify_second_factor(db, u.id, "not-a-code")


def test_recovery_code_is_single_use(db):
    u = create_user(db, "system", "a", "pw-aaaaaaaa", "admin")
    _, codes = setup_totp(db, u.id)
    assert len(codes) == 10
    assert verify_second_factor(db, u.id, codes[0])
    assert not verify_second_factor(db, u.id, codes[0])


def test_password_is_argon2id(db):
    u = create_user(db, "system", "a", "pw-aaaaaaaa", "admin")
    h = db.execute("SELECT password_hash FROM users WHERE id=?", (u.id,)).fetchone()[0]
    assert h.startswith("$argon2id$")


def test_create_user_audited_without_password(db):
    create_user(db, "system", "a", "pw-aaaaaaaa", "admin")
    row = db.execute("SELECT action, new FROM audit").fetchone()
    assert row["action"] == "user.create" and "pw-aaaaaaaa" not in row["new"]
