import sqlite3

conn = sqlite3.connect('../data/store.db')
c = conn.cursor()

c.execute('SELECT DISTINCT zone_id FROM events WHERE store_id = "ST1008"')
print('Zones:', c.fetchall())

c.execute('''
    SELECT event_type, zone_id, timestamp 
    FROM events 
    WHERE store_id = "ST1008" 
    AND (event_type LIKE "%BILLING%" OR zone_id = "BILLING")
    LIMIT 10
''')
print('Billing events:', c.fetchall())

c.execute('''
    SELECT COUNT(DISTINCT e.visitor_id)
    FROM events e, pos_transactions p
    WHERE e.store_id = "ST1008"
    AND e.is_staff = 0
    AND e.zone_id = "BILLING"
    AND p.store_id = "ST1008"
    AND ABS(strftime("%s", e.timestamp) - strftime("%s", p.timestamp)) <= 3600
''')
print('Converted visitors:', c.fetchone()[0])

conn.close()

c.execute('''
    SELECT COUNT(DISTINCT visitor_id)
    FROM events 
    WHERE store_id = "ST1008"
    AND is_staff = 0
    AND event_type IN ("ENTRY", "REENTRY")
''')
print('Unique visitors (is_staff=0):', c.fetchone()[0])

c.execute('''
    SELECT COUNT(DISTINCT visitor_id)
    FROM events 
    WHERE store_id = "ST1008"
    AND is_staff = false
    AND event_type IN ("ENTRY", "REENTRY")
''')
print('Unique visitors (is_staff=false):', c.fetchone()[0])

c.execute('SELECT is_staff, COUNT(*) FROM events WHERE store_id = "ST1008" GROUP BY is_staff')
print('Staff breakdown:', c.fetchall())