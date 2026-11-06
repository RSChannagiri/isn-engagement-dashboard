-- Events held, signups, check-ins, and average turnout per academic term.
SELECT e.term,
       COUNT(DISTINCT e.event_id)                                   AS events,
       COUNT(a.member_id)                                           AS signups,
       COALESCE(SUM(a.checked_in), 0)                               AS checkins,
       COUNT(DISTINCT CASE WHEN a.checked_in = 1 THEN a.member_id END) AS active_members,
       ROUND(1.0 * COALESCE(SUM(a.checked_in), 0) / COUNT(DISTINCT e.event_id), 1) AS avg_turnout
FROM dim_events e
LEFT JOIN fact_attendance a ON a.event_id = e.event_id
GROUP BY e.term
ORDER BY MIN(e.event_date);
