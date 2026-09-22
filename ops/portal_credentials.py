"""Owner-bootstrap-only role creation for Neon; never copied into runtime images.

Neon rejects pre-hashed PASSWORD values. Send the credential as a bound parameter
on the existing verify-full TLS connection, not interpolated client SQL. A
session-local SECURITY INVOKER helper performs the fixed CREATE ROLE. PostgreSQL
hashes the password; Neon also processes the original value in its control plane.

Check existing logging first; do NOT disable audit/logging or grant more rights.
"""
import re


class CredentialLoggingUnsafe(Exception):
    """The existing session logging could expose a credential; fail closed."""


SAFE_LOGGING = {
    'log_min_messages': frozenset({'warning', 'error', 'log', 'fatal', 'panic'}),
    'debug_print_parse': frozenset({'off'}),
    'debug_print_rewritten': frozenset({'off'}),
    'debug_print_plan': frozenset({'off'}),
    'log_statement': frozenset({'none'}),
    'log_min_duration_statement': frozenset({'-1'}),
    'log_min_duration_sample': frozenset({'-1'}),
    'log_transaction_sample_rate': frozenset({'0'}),
    'log_min_error_statement': frozenset({'panic'}),
    'log_error_verbosity': frozenset({'terse'}),
    'log_parameter_max_length_on_error': frozenset({'0'}),
    # The nested CREATE ROLE must not be captured by a nested statement tracker.
    'pg_stat_statements.track': frozenset({None, 'none', 'top'}),
    'auto_explain.log_min_duration': frozenset({None, '-1'}),
    'pgaudit.log': frozenset({None, 'none'}),
}

ROLE_HELPER = """
CREATE FUNCTION pg_temp.richon_create_portal_login(_password text)
RETURNS void LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog
AS $richon_role$
BEGIN
    IF _password IS NULL OR _password !~ '^[A-Za-z0-9_-]{43}$' THEN
        RAISE EXCEPTION 'invalid_bootstrap_password';
    END IF;
    EXECUTE format(
        'CREATE ROLE richon_portal_login LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
        _password
    );
END;
$richon_role$
"""


def check_credential_logging(cur):
    """Only read configuration, with no password in any query or parameter."""
    cur.execute(
        'SELECT name, current_setting(name, true) FROM unnest(%s::text[]) AS settings(name)',
        (list(SAFE_LOGGING),),
    )
    settings = dict(cur.fetchall())
    if set(settings) != set(SAFE_LOGGING) or any(
        settings[name] not in allowed for name, allowed in SAFE_LOGGING.items()
    ):
        raise CredentialLoggingUnsafe()


def create_runtime_role(cur, password):
    """Use only on the dedicated owner connection, inside its DB transaction.

    No SECURITY DEFINER, persistent helper, password literal, file, or logging.
    The temp helper disappears when that connection closes. Retry with an
    already-created managed role never calls this function or changes a password.
    """
    if not isinstance(password, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', password):
        raise ValueError('invalid_bootstrap_password')
    check_credential_logging(cur)
    cur.execute(ROLE_HELPER)
    cur.execute('SELECT pg_temp.richon_create_portal_login(%s)', (password,))
