-- Members who were active earlier but have not checked in during the most recent term.
WITH latest AS (
    SELECT term FROM dim_events ORDER BY event_date DESC LIMIT 1
),
history AS (
    SELECT a.member_id,
           SUM(a.checked_in)                                                      AS lifetime_checkins,
           SUM(CASE WHEN e.term = (SELECT term FROM latest) THEN a.checked_in ELSE 0 END) AS latest_term_checkins,
           MAX(CASE WHEN a.checked_in = 1 THEN e.event_date END)                  AS last_checkin
    FROM fact_attendance a
    JOIN dim_events e ON e.event_id = a.event_id
    GROUP BY a.member_id
)
SELECT m.member_id, m.first_name, m.last_name, m.major, m.class_year,
       h.lifetime_checkins, h.last_checkin
FROM history h
JOIN dim_members m ON m.member_id = h.member_id
WHERE h.lifetime_checkins >= 2 AND h.latest_term_checkins = 0
ORDER BY h.lifetime_checkins DESC, h.last_checkin;
