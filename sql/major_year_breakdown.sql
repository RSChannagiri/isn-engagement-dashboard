-- Members, active members, and check-ins by major and class year.
WITH per_member AS (
    SELECT member_id, SUM(checked_in) AS checkins
    FROM fact_attendance
    GROUP BY member_id
)
SELECT m.major,
       m.class_year,
       COUNT(*)                                          AS members,
       SUM(CASE WHEN p.checkins > 0 THEN 1 ELSE 0 END)   AS active_members,
       COALESCE(SUM(p.checkins), 0)                      AS checkins,
       ROUND(1.0 * COALESCE(SUM(p.checkins), 0) / COUNT(*), 2) AS checkins_per_member
FROM dim_members m
LEFT JOIN per_member p ON p.member_id = m.member_id
GROUP BY m.major, m.class_year
ORDER BY checkins DESC, m.major, m.class_year;
