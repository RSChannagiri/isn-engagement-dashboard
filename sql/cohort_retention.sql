-- Cohort retention: for each join-term cohort, the share of members who checked in during each term.
WITH active AS (
    SELECT DISTINCT a.member_id, e.term, MIN(e.event_date) OVER (PARTITION BY e.term) AS term_start
    FROM fact_attendance a
    JOIN dim_events e ON e.event_id = a.event_id
    WHERE a.checked_in = 1
),
cohort_size AS (
    SELECT join_term, COUNT(*) AS members FROM dim_members GROUP BY join_term
)
SELECT m.join_term                                   AS cohort,
       cs.members                                    AS cohort_size,
       act.term                                      AS active_term,
       COUNT(DISTINCT act.member_id)                 AS active_members,
       ROUND(1.0 * COUNT(DISTINCT act.member_id) / cs.members, 3) AS retention_rate
FROM dim_members m
JOIN cohort_size cs ON cs.join_term = m.join_term
JOIN active act ON act.member_id = m.member_id
GROUP BY m.join_term, act.term
ORDER BY MIN(m.join_date), MIN(act.term_start);
