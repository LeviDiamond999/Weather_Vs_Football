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

result = pl.SQLContext( weather=weather, pbp=pbp).execute("""
    SELECT posteam AS Offense, AVG(epa) AS Avg_EPA, COUNT(DISTINCT(game_id)) AS Games
FROM pbp p
JOIN weather w
      ON p.location_id = w.location_id
      AND p.time_of_day_rounded = w.time_of_day_rounded
WHERE p.roof NOT IN ('closed', 'dome')
AND (w."temperature_2m (°F)" BETWEEN -30 AND 32)
AND (w."rain (mm)" BETWEEN 0 AND 200)
AND (w."snowfall (cm)" BETWEEN 0 AND 6)
AND (w."relative_humidity_2m (%)" BETWEEN 0 AND 110)
AND (w."wind_speed_10m (mp/h)" BETWEEN 0 AND 50)
AND (p.season BETWEEN 2022 AND 2026)
AND (p.kick_distance IS NULL)                                                          
GROUP BY Offense
ORDER BY Avg_EPA DESC
""", eager=True)
print(result)

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

result = pl.SQLContext( weather=weather, pbp=pbp).execute("""
    SELECT defteam AS Defense, AVG(epa) AS Avg_EPA_Allowed, COUNT(DISTINCT(game_id)) AS Games
FROM pbp p
JOIN weather w
      ON p.location_id = w.location_id
      AND p.time_of_day_rounded = w.time_of_day_rounded
WHERE p.roof NOT IN ('closed', 'dome')
AND (w."temperature_2m (°F)" BETWEEN -30 AND 32)
AND (w."rain (mm)" BETWEEN 0 AND 200)
AND (w."snowfall (cm)" BETWEEN 0 AND 6)
AND (w."relative_humidity_2m (%)" BETWEEN 0 AND 110)
AND (w."wind_speed_10m (mp/h)" BETWEEN 0 AND 50)
AND (p.season BETWEEN 2022 AND 2026)
AND p.kick_distance IS NULL 
GROUP BY Defense
ORDER BY Avg_EPA_Allowed ASC
""", eager=True)
print(result)

-- QB Performance
WITH qb_plays AS (
  SELECT *,
    CASE WHEN passer IS NOT NULL THEN passer
         WHEN rusher_is_qb = 1   THEN rusher
    END AS qb_player,
    CASE WHEN passer IS NOT NULL THEN qb_epa
         WHEN rusher_is_qb = 1   THEN epa
    END AS qb_epa_adjusted
  FROM pbp
  WHERE qb_spike = 0
    AND qb_kneel = 0
    AND play_type IN ('pass', 'run')  
)
SELECT qb_player AS QB, 
      AVG(qb_epa_adjusted) AS Avg_EPA, 
      COUNT(*) AS Snaps, 
      SUM(CASE WHEN touchdown = 1 AND td_team = posteam THEN 1 ELSE 0 END) AS TDs 
FROM qb_plays p
JOIN weather w
  ON p.location_id = w.location_id
  AND p.time_of_day_rounded = w.time_of_day_rounded
WHERE p.qb_player IS NOT NULL
AND p.roof NOT IN (r)
AND (w."temperature_2m (°F)" BETWEEN t_1 AND t_2)
AND (w."rain (mm)" BETWEEN p_1 AND p_2)
AND (w."snowfall (cm)" BETWEEN s_1 AND s_2)
AND (w."relative_humidity_2m (%)" BETWEEN h_1 AND h_2)
AND (w."wind_speed_10m (mp/h)" BETWEEN w_1 AND w_2)
AND (p.season BETWEEN y_1 AND y_2)
GROUP BY QB
HAVING COUNT(*) >= 50
ORDER BY Avg_EPA DESC

-- Rushing Performance
roofs_excluded = ["closed", "dome"]
t_1, t_2 = -30, 32       # temperature (°F)
p_1, p_2 = 0, 200        # rain (mm)
s_1, s_2 = 0, 6          # snowfall (cm)
h_1, h_2 = 0, 100        # humidity (%)
w_1, w_2 = 0, 50         # wind (mph)
y_1, y_2 = 2022, 2026    # seasons
min_carries = 20

roof_list = ", ".join(f"'{r}'" for r in roofs_excluded)

result = pl.SQLContext(pbp=pbp, weather=weather).execute(f"""
SELECT rusher_player_name AS Rusher,
       AVG(epa) AS Avg_EPA,
       SUM(rushing_yards) * 1.0 / COUNT(*) AS Yards_per_Carry,
       COUNT(*) AS Carries,
       SUM(CASE WHEN rush_touchdown = 1 THEN 1 ELSE 0 END) AS TDs
FROM pbp p
JOIN weather w
  ON p.location_id = w.location_id
  AND p.time_of_day_rounded = w.time_of_day_rounded
WHERE p.rusher_player_id IS NOT NULL
  AND p.play_type = 'run'
  AND p.qb_scramble = 0
  AND p.two_point_attempt = 0
  AND p.roof NOT IN ({roof_list})
  AND (w."temperature_2m (°F)" BETWEEN {t_1} AND {t_2})
  AND (w."rain (mm)" BETWEEN {p_1} AND {p_2})
  AND (w."snowfall (cm)" BETWEEN {s_1} AND {s_2})
  AND (w."relative_humidity_2m (%)" BETWEEN {h_1} AND {h_2})
  AND (w."wind_speed_10m (mp/h)" BETWEEN {w_1} AND {w_2})
  AND (p.season BETWEEN {y_1} AND {y_2})
GROUP BY p.rusher_player_id, rusher_player_name
HAVING COUNT(*) >= {min_carries}
ORDER BY Avg_EPA DESC
""", eager=True)
print(result)

-- Receiving Performance
roofs_excluded = ["closed", "dome"]
t_1, t_2 = -30, 32       # temperature (°F)
p_1, p_2 = 0, 200        # rain (mm)
s_1, s_2 = 0, 6          # snowfall (cm)
h_1, h_2 = 0, 100        # humidity (%)
w_1, w_2 = 0, 50         # wind (mph)
y_1, y_2 = 2022, 2026    # seasons
min_targets = 20

roof_list = ", ".join(f"'{r}'" for r in roofs_excluded)

result = pl.SQLContext(pbp=pbp, weather=weather).execute(f"""
SELECT receiver_player_name AS Receiver,
       COUNT(*) AS Targets,
       SUM(complete_pass) AS Receptions,
       AVG(complete_pass) AS Catch_Rate,
       AVG(epa) AS Avg_EPA,
       SUM(receiving_yards) * 1.0 / COUNT(*) AS Yards_per_Target,
       SUM(receiving_yards) * 1.0 / COUNT(DISTINCT game_id) AS Yards_per_Game,
       SUM(CASE WHEN pass_touchdown = 1 THEN 1 ELSE 0 END) AS TDs
FROM pbp p
JOIN weather w
  ON p.location_id = w.location_id
  AND p.time_of_day_rounded = w.time_of_day_rounded
WHERE p.receiver_player_id IS NOT NULL
  AND p.play_type = 'pass'
  AND p.two_point_attempt = 0
  AND p.roof NOT IN ({roof_list})
  AND (w."temperature_2m (°F)" BETWEEN {t_1} AND {t_2})
  AND (w."rain (mm)" BETWEEN {p_1} AND {p_2})
  AND (w."snowfall (cm)" BETWEEN {s_1} AND {s_2})
  AND (w."relative_humidity_2m (%)" BETWEEN {h_1} AND {h_2})
  AND (w."wind_speed_10m (mp/h)" BETWEEN {w_1} AND {w_2})
  AND (p.season BETWEEN {y_1} AND {y_2})
GROUP BY p.receiver_player_id, receiver_player_name
HAVING COUNT(*) >= {min_targets}
ORDER BY Avg_EPA DESC
""", eager=True)
print(result)

      
