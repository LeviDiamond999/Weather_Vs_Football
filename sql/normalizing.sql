ALTER TABLE pbp ADD COLUMN "location_id" INT;

UPDATE pbp
SET "location_id" = 
    CASE
        WHEN "stadium_id" = 'LAX01' THEN '26'
        WHEN "stadium_id" = 'LAX01' AND "stadium" = 'Arena Corinthians' THEN '34'
        WHEN "stadium_id" = 'NYC01' THEN '20'
        WHEN "stadium" = 'Tottenham Hotspur Stadium' AND "stadium_id" = 'NYC01' THEN '30'
        WHEN "stadium_id" = 'SFO01' THEN '14'
        WHEN "stadium_id" = 'PHI00' THEN '15'
        WHEN "stadium_id" = 'KAN00' THEN '2'
        WHEN "stadium_id" = 'DET00' THEN '8'
        WHEN "stadium_id" = 'TAM00' THEN '24'
        WHEN "stadium_id" = 'DEN00' THEN '6'
        WHEN "stadium_id" = 'BAL00' THEN '18'
        WHEN "stadium_id" = 'SEA00' THEN '17'
        WHEN "stadium_id" = 'BUF00' THEN '11'
        WHEN "stadium_id" = 'PIT00' THEN '0'
        WHEN "stadium_id" = 'PIT00' AND "stadium" = 'Croke Park' THEN '35'
        WHEN "stadium_id" = 'CHI98' THEN '27'
        WHEN "stadium_id" = 'VEG00' THEN '1'
        WHEN "stadium_id" = 'BOS00' THEN '9'
        WHEN "stadium_id" = 'PHO00' THEN '28'
        WHEN "stadium_id" = 'DAL00' THEN '3'
        WHEN "stadium_id" = 'ATL97' THEN '19'
        WHEN "stadium_id" = 'IND00' THEN '16'
        WHEN "stadium_id" = 'IND00' AND "stadium" = 'Olympic Stadium' THEN '36'
        WHEN "stadium_id" = 'GNB00' THEN '13'
        WHEN "stadium_id" = 'MIA00' THEN '10'
        WHEN "stadium_id" = 'MIA00' AND "stadium" = 'Bernabeu' THEN '37'
        WHEN "stadium_id" = 'HOU00' THEN '25'
        WHEN "stadium_id" = 'CAR00' THEN '4'
        WHEN "stadium_id" = 'NAS00' THEN '21'
        WHEN "stadium_id" = 'CIN00' THEN '23'
        WHEN "stadium_id" = 'MIN01' THEN '29'
        WHEN "stadium_id" = 'WAS00' THEN '22'
        WHEN "stadium_id" = 'NOR00' THEN '5'
        WHEN "stadium_id" = 'CLE00' THEN '12'
        WHEN "stadium_id" = 'JAX00' THEN '7'
        WHEN "stadium_id" = 'LON02' THEN '30'
        WHEN "stadium_id" = 'LON00' THEN '31'
        WHEN "stadium_id" = 'FRA00' THEN '39'
        WHEN "stadium_id" = 'GER00' THEN '32'
        WHEN "stadium_id" = 'SAO00' THEN '34'
        WHEN "stadium_id" = 'MEL00' THEN '38'
        WHEN "stadium_id" = 'MEX00' THEN '33'
        WHEN "stadium_id" = 'RIO00' THEN '40'
        WHEN "stadium" = 'Tottenham Hotspur Stadium' AND "stadium_id" = 'JAX00' THEN '30'
        WHEN "stadium" = 'Wembley Stadium' AND "stadium_id" = 'JAX00' THEN '31'
        ELSE NULL
    END;
    
-- 1. keep a copy of the original values, just in case
ALTER TABLE pbp ADD COLUMN time_of_day_raw text;
UPDATE pbp SET time_of_day_raw = time_of_day;

-- 2. round time_of_day to the nearest hour, in the weather file's format
UPDATE pbp
SET time_of_day = to_char(
      date_trunc('hour',
        (time_of_day::timestamptz AT TIME ZONE 'UTC') + interval '30 minutes'),
      'YYYY-MM-DD"T"HH24:MI')
WHERE time_of_day LIKE '%Z';




    
