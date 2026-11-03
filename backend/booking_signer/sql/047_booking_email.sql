-- Sasha 328 · THE BOOKING EMAIL — two nullable columns, nothing else changes:
--   guest_contacts.booking_email  the ONE address the person named for their bookings ("use tylerwarren@gmail.com for my bookings"),
--                                 on their ONE contact record (contacts.set_booking_email) — given to venues as person.email
--   mailbox_links.address         the linked Gmail's own address (Gmail's profile, read once) — the default booking email, so a
--                                 platform's confirmation and its cancel link arrive where Sasha reads
-- Safe before or after the deploy: until it's applied, saving a booking email says "couldn't be saved — nothing was saved", the
-- mailbox's address isn't kept (logged), and every booking uses the sign-in address as before.
-- ⛔ NOT APPLIED by any session: the founder approves, then it runs via railway run (preview, transaction, verify).

-- preview (read-only): both must be 0
select count(*) from information_schema.columns where table_name = 'guest_contacts' and column_name = 'booking_email';
select count(*) from information_schema.columns where table_name = 'mailbox_links' and column_name = 'address';

begin;
alter table guest_contacts add column booking_email text check (booking_email is null or (char_length(booking_email) <= 254 and booking_email ~ '^[^@\s]+@[^@\s]+\.[a-z]{2,}$'));
alter table mailbox_links add column address text check (address is null or char_length(address) <= 254);
commit;

-- verify: both 1
select count(*) from information_schema.columns where table_name = 'guest_contacts' and column_name = 'booking_email';
select count(*) from information_schema.columns where table_name = 'mailbox_links' and column_name = 'address';
