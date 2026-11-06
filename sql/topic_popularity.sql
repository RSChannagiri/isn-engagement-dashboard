-- Workshop popularity by topic: turnout, show rate, and average fill rate against room capacity.
WITH per_event AS (
    SELECT e.event_id, e.topic, e.capacity,
           COUNT(a.member_id)              AS signups,
           COALESCE(SUM(a.checked_in), 0)  AS checkins
    FROM dim_events e
    LEFT JOIN fact_attendance a ON a.event_id = e.event_id
    GROUP BY e.event_id
)
SELECT topic,
       COUNT(*)                                              AS events,
       SUM(signups)                                          AS signups,
       SUM(checkins)                                         AS checkins,
       ROUND(1.0 * SUM(checkins) / COUNT(*), 1)              AS avg_turnout,
       ROUND(1.0 * SUM(checkins) / NULLIF(SUM(signups), 0), 3) AS show_rate,
       ROUND(AVG(1.0 * checkins / capacity), 3)              AS avg_fill_rate
FROM per_event
GROUP BY topic
ORDER BY avg_turnout DESC;
