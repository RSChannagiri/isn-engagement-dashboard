-- Share of active members who checked in to two or more events.
WITH per_member AS (
    SELECT member_id, SUM(checked_in) AS n
    FROM fact_attendance
    GROUP BY member_id
    HAVING SUM(checked_in) > 0
)
SELECT COUNT(*)                                        AS active_members,
       SUM(CASE WHEN n >= 2 THEN 1 ELSE 0 END)         AS repeat_members,
       ROUND(1.0 * SUM(CASE WHEN n >= 2 THEN 1 ELSE 0 END) / COUNT(*), 3) AS repeat_rate
FROM per_member;
