-- Staged only: no production execution in this PR.
-- An order is visible to a member only through an explicitly verified link.
-- No backfill by name, telephone, email, or provider profile.
CREATE TABLE richon.member_order_links (
    order_id varchar(64) PRIMARY KEY REFERENCES richon.orders(order_id),
    member_id uuid NOT NULL REFERENCES richon.members(member_id),
    linked_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX member_order_links_member_idx ON richon.member_order_links(member_id, order_id);
REVOKE ALL ON richon.member_order_links FROM PUBLIC;
