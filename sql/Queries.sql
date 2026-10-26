-- Offense 
SELECT posteam AS Offense, AVG(epa) AS Avg_EPA, COUNT(DISTINCT(game_id)) AS Games
FROM pbp p
JOIN weather w
      ON p.location_id = w.location_id
      AND p.time_of_day_rounded = w.time_of_day_rounded
WHERE p.roof NOT IN (r)
AND (w."temperature_2m (°F)" BETWEEN t_1 AND t_2)
AND (w."rain (mm)" BETWEEN p_1 AND p_2)
AND (w."snowfall (cm)" BETWEEN s_1 AND s_2)
AND (w."relative_humidity_2m (%)" BETWEEN h_1 AND h_2)
AND (w."wind_speed_10m (mp/h)" BETWEEN w_1 AND w_2)
AND (p.season BETWEEN y_1 AND y_2)
AND p.kick_distance IS NULL 
GROUP BY Offense
ORDER BY Avg_EPA DESC

-- Defense
SELECT defteam AS Defense, AVG(epa) AS Avg_EPA_Allowed, COUNT(DISTINCT(game_id)) AS Games
FROM pbp p
JOIN weather w
      ON p.location_id = w.location_id
      AND p.time_of_day_rounded = w.time_of_day_rounded
WHERE p.roof NOT IN (r)
AND (w."temperature_2m (°F)" BETWEEN t_1 AND t_2)
AND (w."rain (mm)" BETWEEN p_1 AND p_2)
AND (w."snowfall (cm)" BETWEEN s_1 AND s_2)
AND (w."relative_humidity_2m (%)" BETWEEN h_1 AND h_2)
AND (w."wind_speed_10m (mp/h)" BETWEEN w_1 AND w_2)
AND (p.season BETWEEN y_1 AND y_2)
AND p.kick_distance IS NULL 
GROUP BY Defense
ORDER BY Avg_EPA_Allowed ASC

-- Player Performance
SELECT passer, 
