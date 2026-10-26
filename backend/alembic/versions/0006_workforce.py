"""Personnel : conducteurs, permis, habilitations (MODELE_PHYSIQUE_LOT1 §5.6).

Revision ID: 0006
Revises: 0005
"""

from app.core.migration_tools import guard_destructive, run_sql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

UPGRADE = r"""
CREATE TABLE driver (
  driver_id        uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id        uuid NOT NULL,
  site_id          uuid NOT NULL,
  user_account_id  uuid,
  employee_number  text NOT NULL,
  last_name        text NOT NULL,
  first_name       text NOT NULL,
  phone            text,
  employment_type  text NOT NULL DEFAULT 'EMPLOYEE',
  external_company_name text,
  hire_date date, exit_date date,
  status                 text NOT NULL DEFAULT 'ACTIVE',
  unavailability_reason  text,
  unavailable_until      date,
  suspension_reason_code text,
  anonymized_at          timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_driver PRIMARY KEY (driver_id),
  CONSTRAINT fk_driver__tenant FOREIGN KEY (tenant_id) REFERENCES tenant (tenant_id) ON DELETE RESTRICT,
  CONSTRAINT fk_driver__site   FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT fk_driver__user   FOREIGN KEY (tenant_id, user_account_id) REFERENCES user_account (tenant_id, user_account_id) ON DELETE RESTRICT,
  CONSTRAINT uq_driver_tenant_id       UNIQUE (tenant_id, driver_id),
  CONSTRAINT uq_driver_tenant_employee UNIQUE (tenant_id, employee_number),
  CONSTRAINT uq_driver_tenant_user     UNIQUE (tenant_id, user_account_id),
  CONSTRAINT ck_driver_status   CHECK (status IN ('ACTIVE','UNAVAILABLE','SUSPENDED','INACTIVE')),
  CONSTRAINT ck_driver_employment CHECK (employment_type IN ('EMPLOYEE','TEMP_AGENCY','SUBCONTRACTOR')),
  CONSTRAINT ck_driver_external CHECK (employment_type <> 'SUBCONTRACTOR' OR external_company_name IS NOT NULL),
  CONSTRAINT ck_driver_unavail  CHECK ((status = 'UNAVAILABLE') = (unavailability_reason IS NOT NULL)),
  CONSTRAINT ck_driver_unavail_reason CHECK (unavailability_reason IS NULL OR unavailability_reason IN ('LEAVE','TRAINING','OTHER')),
  CONSTRAINT ck_driver_suspension CHECK ((status = 'SUSPENDED') = (suspension_reason_code IS NOT NULL)),
  CONSTRAINT ck_driver_exit     CHECK ((status = 'INACTIVE') = (exit_date IS NOT NULL)),
  CONSTRAINT ck_driver_dates    CHECK (exit_date IS NULL OR hire_date IS NULL OR exit_date >= hire_date),
  CONSTRAINT ck_driver_phone    CHECK (phone IS NULL OR phone ~ '^\+[1-9][0-9]{6,14}$'),
  CONSTRAINT ck_driver_version  CHECK (row_version >= 1)
);
CREATE INDEX ix_driver_tenant_site_status ON driver (tenant_id, site_id, status);
CREATE INDEX ix_driver_tenant_name        ON driver (tenant_id, lower(last_name), lower(first_name));
SELECT app.apply_tenant_rls('driver', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('driver');

CREATE TABLE driver_license (
  driver_license_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id     uuid NOT NULL,
  driver_id     uuid NOT NULL,
  license_number text NOT NULL,
  category_code  text NOT NULL,
  issuing_authority text,
  issue_date  date NOT NULL,
  expiry_date date NOT NULL,
  status      text NOT NULL DEFAULT 'VALID',
  status_note text,
  document_reference text,
  verified_by uuid, verified_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_driver_license PRIMARY KEY (driver_license_id),
  CONSTRAINT fk_driver_license__driver FOREIGN KEY (tenant_id, driver_id) REFERENCES driver (tenant_id, driver_id) ON DELETE RESTRICT,
  CONSTRAINT fk_driver_license__category FOREIGN KEY (category_code) REFERENCES license_category_ref (code) ON DELETE RESTRICT,
  CONSTRAINT fk_driver_license__verified_by FOREIGN KEY (verified_by) REFERENCES user_account (user_account_id) ON DELETE RESTRICT,
  CONSTRAINT uq_driver_license_tenant_id UNIQUE (tenant_id, driver_license_id),
  CONSTRAINT uq_driver_license_issue UNIQUE (tenant_id, driver_id, license_number, category_code, issue_date),
  CONSTRAINT ck_driver_license_dates  CHECK (expiry_date > issue_date),
  CONSTRAINT ck_driver_license_status CHECK (status IN ('VALID','SUSPENDED','WITHDRAWN')),
  CONSTRAINT ck_driver_license_verif  CHECK ((verified_by IS NULL) = (verified_at IS NULL)),
  CONSTRAINT ck_driver_license_version CHECK (row_version >= 1)
);
CREATE INDEX ix_driver_license_driver ON driver_license (tenant_id, driver_id, category_code, expiry_date DESC);
CREATE INDEX ix_driver_license_expiry ON driver_license (tenant_id, expiry_date) WHERE status = 'VALID';
SELECT app.apply_tenant_rls('driver_license', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('driver_license');

CREATE TABLE driver_qualification (
  driver_qualification_id uuid NOT NULL DEFAULT gen_random_uuid(),
  tenant_id  uuid NOT NULL,
  driver_id  uuid NOT NULL,
  qualification_type  text NOT NULL,
  vehicle_category_id uuid,
  site_id             uuid,
  valid_from date NOT NULL,
  valid_to   date,
  status     text NOT NULL DEFAULT 'VALID',
  issued_by_name text, reference text, restrictions text,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid, updated_by uuid, row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT pk_driver_qualification PRIMARY KEY (driver_qualification_id),
  CONSTRAINT fk_dq__driver   FOREIGN KEY (tenant_id, driver_id) REFERENCES driver (tenant_id, driver_id) ON DELETE RESTRICT,
  CONSTRAINT fk_dq__category FOREIGN KEY (tenant_id, vehicle_category_id) REFERENCES vehicle_category (tenant_id, vehicle_category_id) ON DELETE RESTRICT,
  CONSTRAINT fk_dq__site     FOREIGN KEY (tenant_id, site_id) REFERENCES site (tenant_id, site_id) ON DELETE RESTRICT,
  CONSTRAINT uq_dq_tenant_id UNIQUE (tenant_id, driver_qualification_id),
  CONSTRAINT ck_dq_type    CHECK (qualification_type IN ('DRIVING_AUTHORIZATION','SAFETY_TRAINING','OTHER')),
  CONSTRAINT ck_dq_status  CHECK (status IN ('VALID','SUSPENDED','REVOKED')),
  CONSTRAINT ck_dq_category CHECK (qualification_type <> 'DRIVING_AUTHORIZATION' OR vehicle_category_id IS NOT NULL),
  CONSTRAINT ck_dq_dates   CHECK (valid_to IS NULL OR valid_to >= valid_from),
  CONSTRAINT ck_dq_version CHECK (row_version >= 1),
  CONSTRAINT ex_dq_no_overlap EXCLUDE USING gist (
      driver_id WITH =, qualification_type WITH =,
      (COALESCE(vehicle_category_id, '00000000-0000-0000-0000-000000000000'::uuid)) WITH =,
      (COALESCE(site_id,             '00000000-0000-0000-0000-000000000000'::uuid)) WITH =,
      daterange(valid_from, valid_to, '[]') WITH &&)
    WHERE (status = 'VALID')
);
CREATE INDEX ix_dq_driver ON driver_qualification (tenant_id, driver_id, valid_to);
CREATE INDEX ix_dq_expiry ON driver_qualification (tenant_id, valid_to) WHERE status = 'VALID';
SELECT app.apply_tenant_rls('driver_qualification', 'SELECT, INSERT, UPDATE');
SELECT app.apply_touch('driver_qualification');
"""

DOWNGRADE = r"""
DROP TABLE driver_qualification;
DROP TABLE driver_license;
DROP TABLE driver;
"""


def upgrade() -> None:
    run_sql(UPGRADE)


def downgrade() -> None:
    guard_destructive()
    run_sql(DOWNGRADE)
