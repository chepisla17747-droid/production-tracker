-- Production Tracker: create and set up a new, complete database in one command.
--
--   sudo -u postgres psql -X -f database/setup.sql
--
-- Optional settings, each given as -v name=value before -f:
--   dbname          database to create (default production_tracker); it must not exist yet
--   passwords=skip  do not ask for the two runtime roles' passwords (for scripts and tests)
--
-- Then create the first Operations Administrator with database/first_admin.sql; until
-- then nobody can sign in to the new database.
--
-- What it builds: every migration merged into one schema (the live database as of
-- 2026-09-23, baseline plus migrations 001-027, with 028 and 029 folded in), the runtime
-- roles' least-privilege grants, and the reference data: roles, permissions, production
-- units, products and their standard processes. No employee, account, password, session
-- or order is copied. The individual migrations are kept in database/old/migrations for
-- reference and for upgrading a database built before this file existed.
--
-- Roles are shared by the whole server: production_tracker_app and production_tracker_admin
-- are created only if missing. When they are created, psql asks for their passwords at the
-- terminal without echoing them and sends them already hashed, so they never reach the
-- server log. Put the same passwords in .env.app and .env.admin.
--
-- Everything inside the database runs in one transaction: if anything fails, the database
-- is left empty. Drop it (DROP DATABASE <dbname>) and run this file again.

\set ON_ERROR_STOP on
\set QUIET on
\if :{?dbname}
\else
    \set dbname production_tracker
\endif

-- ============================================================================ server level

-- Fails, changing nothing, if the database already exists.
CREATE DATABASE :"dbname" WITH TEMPLATE template0 ENCODING 'UTF8';

SELECT NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'production_tracker_app') AS new_app_role,
       NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'production_tracker_admin') AS new_admin_role
\gset

-- The ordinary role serves every page. The privileged role adds employee, account and
-- catalog writes and inherits everything the ordinary role may do.
SELECT format('CREATE ROLE %I LOGIN', name)
FROM unnest(ARRAY['production_tracker_app', 'production_tracker_admin']) AS name
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = name)
\gexec
SELECT 'GRANT production_tracker_app TO production_tracker_admin WITH INHERIT TRUE'
WHERE NOT pg_has_role('production_tracker_admin', 'production_tracker_app', 'MEMBER')
\gexec

\if :{?passwords}
\else
    \set passwords prompt
\endif
SELECT :'passwords' <> 'skip' AS ask_passwords \gset
\if :ask_passwords
    \if :new_app_role
        \echo 'Password for production_tracker_app (DB_PASSWORD in .env.app):'
        \password production_tracker_app
    \endif
    \if :new_admin_role
        \echo 'Password for production_tracker_admin (DB_PASSWORD in .env.admin):'
        \password production_tracker_admin
    \endif
\endif

GRANT CONNECT ON DATABASE :"dbname" TO production_tracker_app;

\connect :"dbname"
BEGIN;

-- ======================================================================= people and access

CREATE TABLE public.employee (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name         TEXT NOT NULL,
    surname      TEXT NOT NULL,
    email        VARCHAR(256),
    phone_num    VARCHAR(16),
    birth_date   DATE,
    regist_date  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- Set when the employee leaves; their records stay, their access ends.
    left_at      TIMESTAMPTZ,
    CONSTRAINT employee_birth_date_check CHECK (birth_date IS NULL OR birth_date <= CURRENT_DATE)
);
CREATE UNIQUE INDEX employee_email_unique_ci ON public.employee (lower(email));
-- The employee directory pages through this order.
CREATE INDEX employee_name_idx ON public.employee (surname, name, id);

CREATE TABLE public.role (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            TEXT NOT NULL UNIQUE,
    description     TEXT,
    is_system_role  BOOLEAN NOT NULL DEFAULT FALSE,
    -- The one default role every new employee receives (the "Employee" role).
    is_default      BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT default_role_must_be_system CHECK (NOT is_default OR is_system_role)
);
CREATE UNIQUE INDEX role_only_one_default ON public.role (is_default) WHERE is_default = TRUE;

CREATE TABLE public.permission (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    description  TEXT
);

CREATE TABLE public.employee_role (
    employee_id  BIGINT NOT NULL REFERENCES public.employee (id),
    role_id      BIGINT NOT NULL REFERENCES public.role (id) ON DELETE CASCADE,
    PRIMARY KEY (employee_id, role_id)
);

CREATE TABLE public.role_permission (
    role_id        BIGINT NOT NULL REFERENCES public.role (id) ON DELETE CASCADE,
    permission_id  BIGINT NOT NULL REFERENCES public.permission (id),
    PRIMARY KEY (role_id, permission_id)
);

CREATE TABLE public.user_account (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id      BIGINT NOT NULL UNIQUE REFERENCES public.employee (id),
    username         TEXT NOT NULL,
    -- NULL while the account waits for its owner to redeem the activation code.
    password_hash    TEXT,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    last_login_at    TIMESTAMPTZ,
    password_set_at  TIMESTAMPTZ,
    CONSTRAINT pending_password_timestamp_check CHECK (password_hash IS NOT NULL OR password_set_at IS NULL)
);
CREATE UNIQUE INDEX user_account_username_unique_ci ON public.user_account (lower(username));

-- ========================================================================= product catalog

CREATE TABLE public.production_unit (
    id        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name      TEXT NOT NULL,
    location  TEXT,
    -- Inactive units are hidden from the step editor and supervisor list, never deleted.
    active    BOOLEAN NOT NULL DEFAULT TRUE,
    -- A name is unique within its location, and among units without a location.
    CONSTRAINT production_unit_name_location_key UNIQUE NULLS NOT DISTINCT (name, location)
);

CREATE TABLE public.product_type (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reference_code    TEXT UNIQUE,
    name              TEXT NOT NULL,
    description       TEXT,
    is_orderable      BOOLEAN NOT NULL DEFAULT TRUE,
    image             BYTEA,
    image_media_type  TEXT,
    -- The picture's version in page URLs, so browsers keep it until it is replaced.
    image_updated_at  TIMESTAMPTZ,
    CONSTRAINT product_image_complete CHECK ((image IS NULL) = (image_media_type IS NULL)),
    CONSTRAINT product_image_version_check CHECK ((image IS NULL) = (image_updated_at IS NULL))
);

-- A process is one version of a product's route; editing creates the next version, so
-- existing orders keep the route they were planned with.
CREATE TABLE public.process_definition (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_type_id  BIGINT NOT NULL REFERENCES public.product_type (id),
    reference_code   TEXT UNIQUE,
    name             TEXT,
    version          INTEGER NOT NULL,
    is_active        BOOLEAN NOT NULL DEFAULT TRUE,
    CONSTRAINT process_definition_version_check CHECK (version > 0),
    UNIQUE (product_type_id, version)
);

CREATE TABLE public.process_step (
    id                     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name                   TEXT NOT NULL,
    unit_id                BIGINT NOT NULL REFERENCES public.production_unit (id),
    standard_time_seconds  BIGINT,
    instructions           TEXT,
    CONSTRAINT process_step_standard_time_check CHECK (standard_time_seconds IS NULL OR standard_time_seconds > 0)
);

CREATE TABLE public.process_definition_process_step (
    id                     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    process_definition_id  BIGINT NOT NULL REFERENCES public.process_definition (id),
    process_step_id        BIGINT NOT NULL REFERENCES public.process_step (id),
    sequence_number        INTEGER NOT NULL,
    CONSTRAINT process_definition_process_step_sequence_number_check CHECK (sequence_number > 0),
    UNIQUE (process_definition_id, process_step_id),
    UNIQUE (process_definition_id, sequence_number)
);
CREATE INDEX process_definition_process_step_step_idx ON public.process_definition_process_step (process_step_id);

-- ========================================================================== orders and work

CREATE TABLE public.contractor (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name          TEXT NOT NULL,
    email         VARCHAR(256),
    phone_number  VARCHAR(16)
);
-- The contractor directory pages through this order.
CREATE INDEX contractor_name_idx ON public.contractor (name, id);

CREATE TABLE public.work_order (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    order_number     TEXT NOT NULL UNIQUE,
    contractor_id    BIGINT NOT NULL REFERENCES public.contractor (id),
    created_by       BIGINT NOT NULL REFERENCES public.employee (id),
    creation_time    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completion_time  TIMESTAMPTZ,
    is_cancelled     BOOLEAN NOT NULL DEFAULT FALSE,
    notes            TEXT,
    start_date       DATE,
    due_date         DATE,
    CONSTRAINT work_order_check CHECK (completion_time IS NULL OR completion_time >= creation_time),
    CONSTRAINT work_order_schedule_check CHECK (start_date IS NULL OR due_date IS NULL OR due_date >= start_date)
);
-- Orders page, newest first: every order, and each planner's own.
CREATE INDEX work_order_created_idx ON public.work_order (creation_time, id);
CREATE INDEX work_order_creator_created_idx ON public.work_order (created_by, creation_time, id);
-- Order history by completion; open orders (completion_time IS NULL) for the overview,
-- supervisor queue and alerts; orders completed in a statistics period.
CREATE INDEX work_order_completed_idx ON public.work_order (completion_time, id);
-- Cancelled orders are few; statistics counts the executions they hold.
CREATE INDEX work_order_cancelled_idx ON public.work_order (id) WHERE is_cancelled;

CREATE TABLE public.product_instance (
    id                BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    work_order_id     BIGINT NOT NULL REFERENCES public.work_order (id),
    product_type_id   BIGINT NOT NULL REFERENCES public.product_type (id),
    product_code      TEXT UNIQUE,
    creation_time     TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    process_def_id    BIGINT NOT NULL REFERENCES public.process_definition (id),
    scrapped_at       TIMESTAMPTZ,
    scrapped_step_id  BIGINT REFERENCES public.process_step (id),
    CONSTRAINT product_instance_scrap_check CHECK ((scrapped_at IS NULL) = (scrapped_step_id IS NULL))
);
-- Every piece is found through its order.
CREATE INDEX product_instance_work_order_idx ON public.product_instance (work_order_id);

-- One row per piece and route step.
CREATE TABLE public.process_step_execution (
    id                       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_instance_id      BIGINT NOT NULL REFERENCES public.product_instance (id),
    process_step_id          BIGINT NOT NULL REFERENCES public.process_step (id),
    -- Optional plan; schedule delay can be measured only where one is supplied.
    planned_start_time       TIMESTAMPTZ,
    planned_completion_time  TIMESTAMPTZ,
    start_time               TIMESTAMPTZ,
    completion_time          TIMESTAMPTZ,
    creation_time            TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_update_time         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    skipped_at               TIMESTAMPTZ,
    CONSTRAINT process_step_execution_check CHECK (planned_completion_time IS NULL
        OR (planned_start_time IS NOT NULL AND planned_completion_time >= planned_start_time)),
    CONSTRAINT process_step_execution_check1 CHECK (completion_time IS NULL
        OR (start_time IS NOT NULL AND completion_time >= start_time)),
    CONSTRAINT process_step_execution_check2 CHECK (last_update_time >= creation_time),
    CONSTRAINT skipped_execution_not_started CHECK (skipped_at IS NULL
        OR (start_time IS NULL AND completion_time IS NULL)),
    UNIQUE (product_instance_id, process_step_id)
);
-- Executions completed, or skipped, in a statistics period.
CREATE INDEX process_step_execution_completed_idx ON public.process_step_execution (completion_time);
CREATE INDEX process_step_execution_skipped_idx ON public.process_step_execution (skipped_at)
    WHERE skipped_at IS NOT NULL;

-- Who supervises which unit, with history: ended assignments keep valid_until.
CREATE TABLE public.employee_unit_assignment (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    employee_id    BIGINT NOT NULL REFERENCES public.employee (id),
    unit_id        BIGINT NOT NULL REFERENCES public.production_unit (id),
    valid_from     TIMESTAMPTZ NOT NULL,
    valid_until    TIMESTAMPTZ,
    is_supervisor  BOOLEAN NOT NULL DEFAULT FALSE,
    CONSTRAINT employee_unit_assignment_check CHECK (valid_until IS NULL OR valid_until >= valid_from),
    CONSTRAINT employee_unit_assignment_unique UNIQUE NULLS NOT DISTINCT (employee_id, unit_id, valid_from, valid_until)
);
CREATE UNIQUE INDEX unit_one_current_supervisor ON public.employee_unit_assignment (unit_id)
    WHERE is_supervisor AND valid_until IS NULL;

CREATE TABLE public.supervisor_notification (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    supervisor_id    BIGINT NOT NULL REFERENCES public.employee (id),
    work_order_id    BIGINT NOT NULL REFERENCES public.work_order (id),
    process_def_id   BIGINT NOT NULL REFERENCES public.process_definition (id),
    process_step_id  BIGINT NOT NULL REFERENCES public.process_step (id),
    kind             TEXT NOT NULL,
    event_count      INTEGER NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    read_at          TIMESTAMPTZ,
    CONSTRAINT supervisor_notification_kind_check CHECK (kind IN ('assigned', 'ready')),
    CONSTRAINT supervisor_notification_event_count_check CHECK (event_count > 0),
    UNIQUE (supervisor_id, work_order_id, process_def_id, process_step_id, kind)
);

-- One receipt per floor action; request_id makes a repeated submission harmless.
CREATE TABLE public.supervisor_action (
    request_id       UUID PRIMARY KEY,
    supervisor_id    BIGINT NOT NULL REFERENCES public.employee (id),
    work_order_id    BIGINT NOT NULL REFERENCES public.work_order (id),
    process_def_id   BIGINT NOT NULL REFERENCES public.process_definition (id),
    process_step_id  BIGINT NOT NULL REFERENCES public.process_step (id),
    action           TEXT NOT NULL,
    quantity         INTEGER NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reversed_at      TIMESTAMPTZ,
    reversed_by      BIGINT REFERENCES public.employee (id),
    reversal_reason  TEXT,
    CONSTRAINT supervisor_action_action_check CHECK (action IN ('start', 'complete', 'skip', 'scrap')),
    CONSTRAINT supervisor_action_quantity_check CHECK (quantity > 0),
    CONSTRAINT supervisor_action_reversal_check CHECK (
        (reversed_at IS NULL AND reversed_by IS NULL AND reversal_reason IS NULL)
        OR (reversed_at IS NOT NULL AND reversed_by IS NOT NULL AND btrim(reversal_reason) <> ''))
);
CREATE INDEX supervisor_action_work_order_idx ON public.supervisor_action (work_order_id);

-- The executions each action changed, so a manager can reverse exactly those.
CREATE TABLE public.supervisor_action_item (
    request_id    UUID NOT NULL REFERENCES public.supervisor_action (request_id),
    execution_id  BIGINT NOT NULL REFERENCES public.process_step_execution (id),
    PRIMARY KEY (request_id, execution_id)
);

CREATE TABLE public.corrective_request (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id         UUID NOT NULL UNIQUE REFERENCES public.supervisor_action (request_id),
    work_order_id      BIGINT NOT NULL REFERENCES public.work_order (id),
    process_def_id     BIGINT NOT NULL REFERENCES public.process_definition (id),
    process_step_id    BIGINT NOT NULL REFERENCES public.process_step (id),
    quantity           INTEGER NOT NULL,
    kind               TEXT NOT NULL,
    note               TEXT,
    requested_by       BIGINT NOT NULL REFERENCES public.employee (id),
    requested_at       TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_by        BIGINT REFERENCES public.employee (id),
    resolved_at        TIMESTAMPTZ,
    resolution         TEXT,
    replaced_quantity  INTEGER,
    resolution_note    TEXT,
    CONSTRAINT corrective_request_quantity_check CHECK (quantity > 0),
    CONSTRAINT corrective_request_kind_check CHECK (kind IN ('replace', 'review')),
    CONSTRAINT corrective_request_resolution_check CHECK (resolution IN ('replaced', 'closed')),
    CONSTRAINT corrective_request_replaced_quantity_check CHECK (replaced_quantity > 0),
    CONSTRAINT corrective_request_check CHECK ((resolved_at IS NULL) = (resolution IS NULL)
        AND (resolved_at IS NULL) = (resolved_by IS NULL)),
    CONSTRAINT corrective_request_check1 CHECK ((resolution = 'replaced') = (replaced_quantity IS NOT NULL))
);
CREATE INDEX corrective_request_open_idx ON public.corrective_request (work_order_id) WHERE resolved_at IS NULL;

CREATE TABLE public.step_pause (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    work_order_id    BIGINT NOT NULL REFERENCES public.work_order (id),
    process_def_id   BIGINT NOT NULL REFERENCES public.process_definition (id),
    process_step_id  BIGINT NOT NULL REFERENCES public.process_step (id),
    reason           TEXT NOT NULL,
    note             TEXT,
    paused_by        BIGINT NOT NULL REFERENCES public.employee (id),
    paused_at        TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    resumed_by       BIGINT REFERENCES public.employee (id),
    resumed_at       TIMESTAMPTZ,
    CONSTRAINT step_pause_reason_check CHECK (reason IN ('break', 'machine', 'material', 'quality', 'other')),
    CONSTRAINT step_pause_check CHECK ((resumed_at IS NULL) = (resumed_by IS NULL)
        AND (resumed_at IS NULL OR resumed_at >= paused_at))
);
CREATE UNIQUE INDEX step_pause_one_open ON public.step_pause (work_order_id, process_def_id, process_step_id)
    WHERE resumed_at IS NULL;
CREATE INDEX step_pause_step_idx ON public.step_pause (work_order_id, process_def_id, process_step_id);
-- Pauses begun in a statistics period.
CREATE INDEX step_pause_paused_idx ON public.step_pause (paused_at);

-- ============================================================== append-only change records

CREATE TABLE public.role_change (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    changed_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actor_employee_id   BIGINT NOT NULL REFERENCES public.employee (id),
    target_employee_id  BIGINT NOT NULL REFERENCES public.employee (id),
    role_name           TEXT NOT NULL,
    action              TEXT NOT NULL,
    CONSTRAINT role_change_action_check CHECK (action IN ('granted', 'revoked'))
);
CREATE INDEX role_change_target_idx ON public.role_change (target_employee_id, changed_at DESC);

CREATE TABLE public.account_change (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    changed_at          TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actor_employee_id   BIGINT NOT NULL REFERENCES public.employee (id),
    target_employee_id  BIGINT NOT NULL REFERENCES public.employee (id),
    action              TEXT NOT NULL,
    CONSTRAINT account_change_action_check CHECK (action IN (
        'employee_created', 'employee_details_edited', 'account_created', 'account_edited',
        'activation_code_reissued', 'activation_code_revoked', 'password_reset',
        'account_disabled', 'account_enabled', 'employee_left', 'employee_returned'))
);
CREATE INDEX account_change_target_idx ON public.account_change (target_employee_id, changed_at DESC);

-- ================================================================== sign-in and activation

CREATE SCHEMA auth_private;

-- Only digests are stored: a stolen table cannot be replayed as a session.
CREATE TABLE auth_private.session (
    token_digest       TEXT PRIMARY KEY,
    account_id         BIGINT NOT NULL REFERENCES public.user_account (id) ON DELETE CASCADE,
    employee_id        BIGINT NOT NULL REFERENCES public.employee (id),
    credential_digest  TEXT NOT NULL,
    selected_role      TEXT NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at         TIMESTAMPTZ NOT NULL,
    CONSTRAINT session_token_digest_check CHECK (length(token_digest) = 64),
    CONSTRAINT session_credential_digest_check CHECK (length(credential_digest) = 64),
    CONSTRAINT session_selected_role_check CHECK (selected_role IN
        ('planner', 'supervisor', 'manager', 'admin', 'hr', 'operations_admin')),
    CONSTRAINT session_check CHECK (expires_at > created_at)
);
CREATE INDEX session_account_idx ON auth_private.session (account_id);
CREATE INDEX session_expiry_idx ON auth_private.session (expires_at);

CREATE TABLE auth_private.login_attempt (
    subject_digest     TEXT PRIMARY KEY,
    window_started_at  TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    attempts           INTEGER NOT NULL,
    CONSTRAINT login_attempt_subject_digest_check CHECK (length(subject_digest) = 64),
    CONSTRAINT login_attempt_attempts_check CHECK (attempts > 0)
);
CREATE INDEX login_attempt_window_idx ON auth_private.login_attempt (window_started_at);

CREATE SCHEMA account_private;

-- Activation codes: only the SHA-256 digest of the normalized code is stored.
CREATE TABLE account_private.account_token (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id    BIGINT NOT NULL REFERENCES public.user_account (id),
    token_digest  TEXT NOT NULL UNIQUE,
    purpose       TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at    TIMESTAMPTZ NOT NULL,
    consumed_at   TIMESTAMPTZ,
    revoked_at    TIMESTAMPTZ,
    CONSTRAINT account_token_token_digest_check CHECK (length(token_digest) = 64),
    CONSTRAINT account_token_purpose_check CHECK (purpose IN ('invitation', 'password_reset')),
    CONSTRAINT account_token_check CHECK (expires_at > created_at)
);
CREATE INDEX account_token_account_idx ON account_private.account_token (account_id);
CREATE INDEX account_token_expiry_idx ON account_private.account_token (expires_at);

-- ===================================================================== rules kept in the DB

-- Every new employee receives the default role.
CREATE FUNCTION public.assign_default_role() RETURNS trigger LANGUAGE plpgsql AS $function$
DECLARE
    default_role_id BIGINT;
BEGIN
    SELECT id
    INTO default_role_id
    FROM role
    WHERE is_default = TRUE;

    IF default_role_id IS NULL THEN
        RAISE EXCEPTION 'No default role has been configured';
    END IF;

    INSERT INTO employee_role (
        employee_id,
        role_id
    )
    VALUES (
        NEW.id,
        default_role_id
    );

    RETURN NEW;
END;
$function$;
CREATE TRIGGER assign_default_role_trigger AFTER INSERT ON public.employee
    FOR EACH ROW EXECUTE FUNCTION public.assign_default_role();

CREATE FUNCTION public.ensure_exactly_one_default_role() RETURNS trigger LANGUAGE plpgsql AS $function$
BEGIN
    IF (SELECT COUNT(*) FROM role WHERE is_default = TRUE) <> 1 THEN
        RAISE EXCEPTION 'There must be exactly one default role';
    END IF;

    RETURN NULL;
END;
$function$;
CREATE CONSTRAINT TRIGGER exactly_one_default_role AFTER INSERT OR UPDATE OR DELETE ON public.role
    DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.ensure_exactly_one_default_role();

-- The last usable Operations Administrator can be neither removed nor disabled, even in SQL.
CREATE FUNCTION public.keep_one_operations_admin() RETURNS trigger LANGUAGE plpgsql AS $function$
DECLARE
    target BIGINT := OLD.employee_id;
BEGIN
    IF TG_TABLE_NAME = 'employee_role' THEN
        IF NOT EXISTS (SELECT 1 FROM public.role
                       WHERE id = OLD.role_id AND name = 'operations_admin') THEN
            RETURN OLD;
        END IF;
    ELSIF (NEW.is_active OR NOT OLD.is_active)
          AND (NEW.password_hash IS NOT NULL OR OLD.password_hash IS NULL) THEN
        RETURN NEW;  -- the account stays as usable as it was
    ELSIF NOT EXISTS (SELECT 1 FROM public.employee_role er
                      JOIN public.role r ON r.id = er.role_id
                      WHERE er.employee_id = target AND r.name = 'operations_admin') THEN
        RETURN NEW;
    END IF;
    -- One change at a time, so two concurrent removals cannot each see the other's
    -- administrator as the remaining one. The services take the same lock.
    PERFORM pg_advisory_xact_lock(hashtext('tracker.operations_admin'));
    IF NOT EXISTS (
        SELECT 1 FROM public.employee_role er
        JOIN public.role r ON r.id = er.role_id AND r.name = 'operations_admin'
        JOIN public.user_account a ON a.employee_id = er.employee_id
        WHERE er.employee_id <> target AND a.is_active AND a.password_hash IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'At least one usable Operations Administrator must remain'
            USING ERRCODE = 'CH001';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$function$;
CREATE TRIGGER keep_one_operations_admin BEFORE DELETE ON public.employee_role
    FOR EACH ROW EXECUTE FUNCTION public.keep_one_operations_admin();
CREATE TRIGGER keep_one_operations_admin BEFORE UPDATE OF is_active, password_hash ON public.user_account
    FOR EACH ROW EXECUTE FUNCTION public.keep_one_operations_admin();

-- Change records can be added, never rewritten, even by the table owner.
CREATE FUNCTION public.role_change_append_only() RETURNS trigger LANGUAGE plpgsql AS $function$
BEGIN
    RAISE EXCEPTION 'role_change is append-only: % is not allowed', TG_OP;
END;
$function$;
CREATE TRIGGER role_change_no_rewrite BEFORE UPDATE OR DELETE ON public.role_change
    FOR EACH ROW EXECUTE FUNCTION public.role_change_append_only();
CREATE TRIGGER account_change_no_rewrite BEFORE UPDATE OR DELETE ON public.account_change
    FOR EACH ROW EXECUTE FUNCTION public.role_change_append_only();

-- ========================================================================= runtime grants
-- The application never connects as the owner. Nothing may DELETE except sessions and
-- sign-in throttling rows, and role removal by the privileged role.

GRANT USAGE ON SCHEMA public, auth_private TO production_tracker_app;
GRANT USAGE ON SCHEMA auth_private, account_private TO production_tracker_admin;

-- Ordinary role: reads every business table (not the change records), writes floor work.
GRANT SELECT ON public.employee, public.role, public.permission, public.employee_role,
    public.role_permission, public.user_account, public.production_unit, public.product_type,
    public.process_definition, public.process_step, public.process_definition_process_step,
    public.contractor, public.work_order, public.product_instance, public.process_step_execution,
    public.employee_unit_assignment, public.supervisor_notification, public.supervisor_action,
    public.supervisor_action_item, public.corrective_request, public.step_pause
    TO production_tracker_app;
GRANT INSERT, UPDATE ON public.contractor, public.work_order, public.product_instance,
    public.process_step_execution, public.employee_unit_assignment, public.supervisor_notification,
    public.corrective_request TO production_tracker_app;
GRANT INSERT ON public.supervisor_action, public.supervisor_action_item, public.step_pause
    TO production_tracker_app;
-- Own password and contact details, reversing a floor action, resuming a pause.
GRANT UPDATE (password_hash, password_set_at, last_login_at) ON public.user_account TO production_tracker_app;
GRANT UPDATE (email, phone_num) ON public.employee TO production_tracker_app;
GRANT UPDATE (reversed_at, reversed_by, reversal_reason) ON public.supervisor_action TO production_tracker_app;
GRANT UPDATE (resumed_at, resumed_by) ON public.step_pause TO production_tracker_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON auth_private.session, auth_private.login_attempt
    TO production_tracker_app;
GRANT SELECT, USAGE ON SEQUENCE public.contractor_id_seq, public.employee_id_seq,
    public.employee_unit_assignment_id_seq, public.permission_id_seq, public.process_definition_id_seq,
    public.process_definition_process_step_id_seq, public.process_step_execution_id_seq,
    public.process_step_id_seq, public.product_instance_id_seq, public.product_type_id_seq,
    public.production_unit_id_seq, public.role_id_seq, public.user_account_id_seq,
    public.work_order_id_seq TO production_tracker_app;
GRANT USAGE ON SEQUENCE public.corrective_request_id_seq, public.step_pause_id_seq,
    public.supervisor_notification_id_seq TO production_tracker_app;

-- Privileged role, used only for administrator pages: employees, accounts, roles and the
-- catalog, plus the change records. It inherits everything above.
GRANT INSERT, UPDATE ON public.employee, public.user_account, public.production_unit,
    public.product_type, public.process_definition, public.process_step,
    public.process_definition_process_step, public.employee_unit_assignment
    TO production_tracker_admin;
GRANT INSERT, DELETE ON public.employee_role TO production_tracker_admin;
GRANT SELECT, INSERT ON public.role_change, public.account_change TO production_tracker_admin;
GRANT SELECT, INSERT, UPDATE ON account_private.account_token TO production_tracker_admin;
GRANT SELECT, INSERT, UPDATE, DELETE ON auth_private.session, auth_private.login_attempt
    TO production_tracker_admin;
GRANT USAGE ON SEQUENCE public.employee_id_seq, public.user_account_id_seq,
    public.production_unit_id_seq, public.product_type_id_seq, public.process_definition_id_seq,
    public.process_step_id_seq, public.process_definition_process_step_id_seq,
    public.employee_unit_assignment_id_seq, public.role_change_id_seq, public.account_change_id_seq,
    account_private.account_token_id_seq TO production_tracker_admin;

-- ========================================================================= reference data

INSERT INTO public.role (name, description, is_system_role, is_default) VALUES
    ('Employee', 'Default role containing basic employee permissions', TRUE, TRUE),
    ('planner', NULL, FALSE, FALSE),
    ('supervisor', NULL, FALSE, FALSE),
    ('manager', NULL, FALSE, FALSE),
    ('admin', NULL, FALSE, FALSE),
    ('operations_admin', NULL, FALSE, FALSE);

INSERT INTO public.permission (name, description) VALUES
    ('contractor.manage', 'Create and edit contractor contact details'),
    ('contractor.view', 'View contractors for production planning'),
    ('employee.create', 'Add employee records'),
    ('employee.edit.other', 'Change other employees'' records'),
    ('employee.edit.self', 'Change own employee record'),
    ('employee.view.other', 'View other employees'' records'),
    ('production.correct', 'Reverse a mistaken floor action, with a recorded reason'),
    ('production.execute', 'View and update own assigned production parts and notifications'),
    ('production_unit.assign_supervisor', 'Assign and unassign the current supervisor of a production unit'),
    ('production_unit.manage', 'Manage production units and their current supervisor'),
    ('product.manage', 'Create and edit products, processes and process steps'),
    ('role.assign', 'Give employees their website roles, except the administrator role'),
    ('statistics.view.all', 'View production statistics for every authorized process'),
    ('statistics.view.unit', 'View production statistics for currently supervised production units'),
    ('user_account.basic.edit.self', 'Change own password and last login'),
    ('user_account.complete.edit.other', 'Change all employees'' account details'),
    ('user_account.complete.edit.self', 'Change all own account details'),
    ('user_account.complete.view.other', 'View all employees'' account details'),
    ('user_account.create', 'Create pending user accounts and invite their owner'),
    ('user_account.view.self', 'View own account details'),
    ('work_order.create', 'Create production orders and browse the planning catalog'),
    ('work_order.edit.all', 'Edit or cancel any work order'),
    ('work_order.edit.own', 'Edit or cancel the work orders one created'),
    ('work_order.overview', 'View the factory overview and every work order''s progress');

-- The Employee role deliberately holds no permission: sign-in needs one of the other roles.
INSERT INTO public.role_permission (role_id, permission_id)
SELECT role.id, permission.id
FROM (VALUES
    ('planner', ARRAY['contractor.manage', 'contractor.view', 'employee.edit.self',
        'production_unit.assign_supervisor', 'statistics.view.all', 'user_account.basic.edit.self',
        'user_account.view.self', 'work_order.create', 'work_order.edit.own']),
    ('supervisor', ARRAY['employee.edit.self', 'production.execute', 'statistics.view.unit',
        'user_account.basic.edit.self', 'user_account.view.self']),
    ('manager', ARRAY['employee.edit.self', 'production.correct', 'production_unit.assign_supervisor',
        'production_unit.manage', 'statistics.view.all', 'user_account.basic.edit.self',
        'user_account.view.self', 'work_order.edit.all', 'work_order.overview']),
    ('admin', ARRAY['contractor.manage', 'contractor.view', 'employee.create', 'employee.edit.other',
        'employee.edit.self', 'employee.view.other', 'production.correct', 'production.execute',
        'production_unit.assign_supervisor', 'production_unit.manage', 'product.manage', 'role.assign',
        'statistics.view.all', 'statistics.view.unit', 'user_account.basic.edit.self',
        'user_account.complete.edit.other', 'user_account.complete.edit.self',
        'user_account.complete.view.other', 'user_account.create', 'user_account.view.self',
        'work_order.create', 'work_order.edit.all', 'work_order.overview']),
    ('operations_admin', ARRAY['employee.create', 'employee.edit.other', 'employee.edit.self',
        'employee.view.other', 'production_unit.assign_supervisor', 'production_unit.manage',
        'product.manage', 'role.assign', 'user_account.basic.edit.self',
        'user_account.complete.edit.other', 'user_account.complete.view.other',
        'user_account.create', 'user_account.view.self'])
) AS grants (role_name, permission_names)
CROSS JOIN LATERAL unnest(grants.permission_names) AS granted (permission_name)
JOIN public.role ON role.name = grants.role_name
JOIN public.permission ON permission.name = granted.permission_name;

INSERT INTO public.production_unit (name) VALUES
    ('Cutting'), ('Bending'), ('Rolling / Bending'), ('Drilling'), ('Assembly'),
    ('Tack Assembly'), ('Welding'), ('Painting'), ('Final Assembly');

INSERT INTO public.product_type (reference_code, name, description) VALUES
    ('CP-04', 'Cassava Planter', 'Double-row planting attachment'),
    ('BK-01', 'Bung Kee', 'Pickup truck bucket'),
    ('SW-01', 'Steel Wheel', 'Steel wheel'),
    ('GC-01', 'Grass Cutter', 'Grass cutting machine'),
    ('CD-01', 'Short-Neck Cassava Digger', 'Short-neck cassava digging machine'),
    ('RP-01', 'Ridging Plow', 'Ridging plow');

-- Version 1 of each product's standard route, coded <product>-STANDARD.
INSERT INTO public.process_definition (product_type_id, reference_code, name, version)
SELECT id, reference_code || '-STANDARD', 'Standard production', 1 FROM public.product_type;

-- Each route step is its own row, named after its unit, with its standard time in seconds.
DO $routes$
DECLARE
    step RECORD;
    new_step BIGINT;
BEGIN
    FOR step IN
        SELECT d.id AS process_id, route.seq, u.id AS unit_id, route.unit, route.seconds, route.instructions
        FROM (VALUES
            ('CP-04', 1, 'Cutting', 1392, NULL), ('CP-04', 2, 'Assembly', 1800, NULL),
            ('CP-04', 3, 'Welding', 2580, NULL), ('CP-04', 4, 'Painting', 21600, NULL),
            ('BK-01', 1, 'Cutting', 1200, NULL), ('BK-01', 2, 'Rolling / Bending', 360, NULL),
            ('BK-01', 3, 'Assembly', 1560, NULL), ('BK-01', 4, 'Welding', 2220, NULL),
            ('BK-01', 5, 'Painting', 10800, NULL), ('BK-01', 6, 'Final Assembly', 180, NULL),
            ('SW-01', 1, 'Cutting', 1320, NULL), ('SW-01', 2, 'Bending', 480, NULL),
            ('SW-01', 3, 'Rolling / Bending', 210, NULL), ('SW-01', 4, 'Assembly', 600, NULL),
            ('SW-01', 5, 'Welding', 1500, NULL), ('SW-01', 6, 'Painting', 10800, NULL),
            ('GC-01', 1, 'Cutting', 3330, NULL), ('GC-01', 2, 'Bending', 840, NULL),
            ('GC-01', 3, 'Drilling', 300, NULL), ('GC-01', 4, 'Tack Assembly', 3420, NULL),
            ('GC-01', 5, 'Welding', 11340,
                E'1. Part Welding (64 min)\n2. Tack Welding (65 min)\n3. Frame Welding (1 hr)'),
            ('GC-01', 6, 'Painting', 2220, NULL), ('GC-01', 7, 'Final Assembly', 900, NULL),
            ('CD-01', 1, 'Cutting', 1680, NULL), ('CD-01', 2, 'Tack Assembly', 4620, NULL),
            ('CD-01', 3, 'Welding', 21120,
                E'1. Part Welding (205 min)\n2. Tack Welding (87 min)\n3. Frame Welding (1 hr)'),
            ('CD-01', 4, 'Painting', 1800, NULL), ('CD-01', 5, 'Final Assembly', 900, NULL),
            ('RP-01', 1, 'Cutting', 1260, NULL), ('RP-01', 2, 'Bending', 300, NULL),
            ('RP-01', 3, 'Drilling', 120, NULL), ('RP-01', 4, 'Tack Assembly', 1140, NULL),
            ('RP-01', 5, 'Welding', 2580,
                E'1. Part Welding (18 min)\n2. Tack Welding (5 min)\n3. Frame Welding (20 min)'),
            ('RP-01', 6, 'Painting', 600, NULL), ('RP-01', 7, 'Final Assembly', 300, NULL)
        ) AS route (product, seq, unit, seconds, instructions)
        JOIN public.process_definition d ON d.reference_code = route.product || '-STANDARD'
        JOIN public.production_unit u ON u.name = route.unit
        ORDER BY route.product, route.seq
    LOOP
        INSERT INTO public.process_step (name, unit_id, standard_time_seconds, instructions)
        VALUES (step.unit, step.unit_id, step.seconds, step.instructions)
        RETURNING id INTO new_step;
        INSERT INTO public.process_definition_process_step (process_definition_id, process_step_id, sequence_number)
        VALUES (step.process_id, new_step, step.seq);
    END LOOP;
END
$routes$;

-- A mistyped name above would silently drop a row; refuse to finish instead.
DO $check$
BEGIN
    IF (SELECT count(*) FROM public.role_permission) <> 59
       OR (SELECT count(*) FROM public.process_definition_process_step) <> 35
       OR (SELECT count(*) FROM public.process_definition) <> 6 THEN
        RAISE EXCEPTION 'Reference data is incomplete; nothing was created';
    END IF;
END
$check$;

COMMIT;

\echo
\echo 'Database' :"dbname" 'is ready. Next, create its first Operations Administrator:'
\echo '  psql -X -d' :"dbname" '-v admin_username=<username> -f database/first_admin.sql'
