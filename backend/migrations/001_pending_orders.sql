-- Applied explicitly by migrate_orders.py, inside its transaction.
-- No real course, price, customer, or test order is seeded by this migration.
CREATE TABLE richon.courses (
    course_id varchar(64) PRIMARY KEY CHECK (course_id ~ '^[a-z0-9][a-z0-9_-]*$'),
    title varchar(200) NOT NULL CHECK (length(btrim(title)) > 0),
    cohort varchar(100),
    price_krw integer NOT NULL CHECK (price_krw > 0),
    enabled boolean NOT NULL DEFAULT FALSE,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE richon.orders (
    order_id varchar(36) PRIMARY KEY CHECK (order_id ~ '^ord_[a-f0-9]{32}$'),
    idempotency_key uuid NOT NULL UNIQUE,
    request_fingerprint char(64) NOT NULL CHECK (request_fingerprint ~ '^[a-f0-9]{64}$'),
    course_id varchar(64) NOT NULL REFERENCES richon.courses(course_id),
    course_title varchar(200) NOT NULL,
    cohort varchar(100),
    amount_krw integer NOT NULL CHECK (amount_krw > 0),
    currency varchar(3) NOT NULL DEFAULT 'KRW' CHECK (currency = 'KRW'),
    -- Only pending orders exist in this stage. A future migration will add
    -- payment states together with server-side PG verification/transitions.
    status varchar(32) NOT NULL DEFAULT 'pending_payment' CHECK (status = 'pending_payment'),
    customer_name varchar(80) NOT NULL CHECK (length(btrim(customer_name)) > 0),
    customer_phone varchar(11) NOT NULL CHECK (customer_phone ~ '^01[016789][0-9]{7,8}$'),
    customer_email varchar(254) NOT NULL CHECK (length(customer_email) > 2),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX orders_course_created_idx ON richon.orders (course_id, created_at);
REVOKE ALL ON richon.courses, richon.orders FROM PUBLIC;
