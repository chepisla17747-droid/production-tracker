-- Production Tracker: create the first Operations Administrator of a database built with setup.sql.
--
--   sudo -u postgres psql -X -d production_tracker -v admin_username=ops.admin -f database/first_admin.sql
--
-- Settings, each given as -v name=value before -f:
--   admin_username              required: the new account's username
--   admin_name, admin_surname   the person's name (default "Operations Administrator")
--
-- It adds the employee with the operations_admin role and a pending account, and prints a
-- one-time activation code, valid 7 days. Hand over the username and code in person; the
-- owner chooses a password at /activate on the website. Only the code's SHA-256 digest is
-- stored. Everyone else is then added on the website's Operations page.
--
-- Refused while an Operations Administrator can already sign in, so this file cannot be
-- used to add administrators behind the website's back. If the code expired unused, run it
-- again with a different username; the old pending account can be disabled later.

\set ON_ERROR_STOP on
\set QUIET on
\if :{?admin_username}
\else
    \set admin_username ''
\endif
\if :{?admin_name}
\else
    \set admin_name Operations
\endif
\if :{?admin_surname}
\else
    \set admin_surname Administrator
\endif

BEGIN;

CREATE TEMPORARY TABLE first_admin ON COMMIT DROP AS
SELECT btrim(:'admin_username') AS username, btrim(:'admin_name') AS name,
       btrim(:'admin_surname') AS surname, NULL::text AS code;

-- A pending account, exactly as the Operations page creates one: no password until its
-- owner redeems the code on the activation page. Characters come from gen_random_uuid()'s
-- random bytes, with rejection sampling so each of the 31 characters is equally likely.
DO $bootstrap$
DECLARE
    alphabet CONSTANT TEXT := 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';
    admin RECORD;
    raw TEXT := '';
    bytes BYTEA;
    byte_value INTEGER;
    new_employee BIGINT;
    new_account BIGINT;
BEGIN
    SELECT * INTO admin FROM first_admin;
    IF admin.username = '' OR length(admin.username) > 256 OR admin.name = '' OR admin.surname = ''
       OR length(admin.name) > 256 OR length(admin.surname) > 256 THEN
        RAISE EXCEPTION 'Give -v admin_username=<username>; username, admin_name and admin_surname must be 1 to 256 characters';
    END IF;
    IF EXISTS (
        SELECT 1 FROM public.user_account AS account
        JOIN public.employee_role AS held ON held.employee_id = account.employee_id
        JOIN public.role ON role.id = held.role_id
        WHERE role.name = 'operations_admin' AND account.is_active AND account.password_hash IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'An Operations Administrator can already sign in. Add further accounts on the website''s Operations page.';
    END IF;
    WHILE length(raw) < 8 LOOP
        bytes := uuid_send(gen_random_uuid());
        FOR i IN 0..15 LOOP
            -- Bytes 6 and 8 carry the UUID version and variant bits, not randomness.
            CONTINUE WHEN i IN (6, 8);
            byte_value := get_byte(bytes, i);
            IF byte_value < 248 AND length(raw) < 8 THEN  -- 248 = 8 x 31
                raw := raw || substr(alphabet, byte_value % 31 + 1, 1);
            END IF;
        END LOOP;
    END LOOP;
    INSERT INTO public.employee (name, surname) VALUES (admin.name, admin.surname)
    RETURNING id INTO new_employee;
    INSERT INTO public.employee_role (employee_id, role_id)
    SELECT new_employee, id FROM public.role WHERE name = 'operations_admin';
    INSERT INTO public.user_account (employee_id, username, password_hash)
    VALUES (new_employee, admin.username, NULL)
    RETURNING id INTO new_account;
    INSERT INTO account_private.account_token (account_id, token_digest, purpose, expires_at)
    VALUES (new_account, encode(sha256(convert_to(raw, 'UTF8')), 'hex'), 'invitation',
            CURRENT_TIMESTAMP + interval '7 days');
    UPDATE first_admin SET code = substr(raw, 1, 4) || '-' || substr(raw, 5, 4);
END
$bootstrap$;
-- Kept in psql's memory only, to print after the commit succeeds.
SELECT username AS first_admin_username, code AS first_admin_code FROM first_admin \gset

COMMIT;

\echo
\echo 'First Operations Administrator. Hand over the username and code in person; they set a'
\echo 'password at /activate on the website. The code is shown only now and expires in 7 days.'
\echo '  Username:        ' :first_admin_username
\echo '  Activation code: ' :first_admin_code
