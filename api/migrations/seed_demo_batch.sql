-- Testcharge für die Demo: verknüpft einen Schlag des Musterbetriebs mit einer Test GTIN.
-- NUR für Test und Demo. Die GTIN 2000000000015 liegt im Bereich für interne Nummern (beginnt mit 2)
-- und kollidiert mit keinem echten Handelsprodukt.
-- <FIELD_ID> durch die ID von Schlag Nord ersetzen.

WITH b AS (
  INSERT INTO batches (label, buyer, crop, harvest_year, region_code)
  VALUES ('Demo Charge Winterweizen 2026', 'Demo Genossenschaft', 'Winterweizen', 2026, 'AT-5')
  RETURNING id
), f AS (
  INSERT INTO batch_fields (batch_id, field_id, share, consent_at)
  SELECT id, '<FIELD_ID>'::uuid, 1.0, now() FROM b
  RETURNING batch_id
)
INSERT INTO product_batches (gtin, batch_id, valid_from)
SELECT '2000000000015', batch_id, date '2026-08-01' FROM f;
