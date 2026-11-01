-- An authenticator set up but not yet proven with a code. It becomes totp_secret on the first correct code.
ALTER TABLE users ADD COLUMN totp_pending TEXT;
