-- SQLite
CREATE TABLE food(
    fdc_id INTEGER PRIMARY KEY,
    data_type TEXT,
    description TEXT,
    food_category_id INTEGER,
    publication_date TEXT
);
SELECT * FROM food;

DROP TABLE food;
CREATE TABLE food(
    fdc_id INTEGER,
    data_type TEXT,
    description TEXT, 
    food_category_id INTEGER, 
    publication_date TEXT
);
SELECT * FROM food; 
CREATE TABLE food_nutrient(
    id INTEGER PRIMARY KEY,
    fdc_id INTEGER NOT NULL,
    nutrient_id INTEGER NOT NULL,
    amount INTEGER,
    data_points INTEGER,
    derivation_id INTEGER,
    min INTEGER,
    max INTEGER,
    median INTEGER,
    footnote TEXT,
    min_year_acquired INTEGER,
    FOREIGN KEY (fdc_id) REFERENCES food(fdc_id)
);
CREATE TABLE nutrient(
    id INTEGER PRIMARY KEY,
    name TEXT,
    unit_name TEXT,
    nutrient_nbr INTEGER UNIQUE,
    rank INTEGER
);

SELECT
    f.fdc_id,
    f.description,
    fn.nutrient_id,
    fn.amount
FROM food f
JOIN food_nutrient fn
ON f.fdc_id = fn.fdc_id
LIMIT 20;

SELECT 
    f.fdc_id,
    f.description,
    n.id,
    n.name AS nutrient,
    fn.amount,
    n.unit_name
FROM food f
JOIN food_nutrient fn
ON f.fdc_id = fn.fdc_id
JOIN nutrient n
ON fn.nutrient_id = n.nutrient_nbr;

SELECT * FROM food LIMIT 5;
SELECT * FROM food_nutrient LIMIT 5;
SELECT * FROM nutrient LIMIT 5;
SELECT id, name, unit_name FROM nutrient WHERE id IN (301, 307, 1003, 1004, 1005, 1008, 1063, 1093);

SELECT DISTINCT nutrient_id
FROM food_nutrient
WHERE nutrient_id IN (301,307,1003,1004,1005,1008,1063,1093);

SELECT DISTINCT nutrient_id
FROM food_nutrient
GROUP BY nutrient_id
LIMIT 50;

SELECT id, name, unit_name
FROM nutrient
WHERE id IN (301, 307, 319, 337);

CREATE VIEW ingredient_master AS
SELECT
    f.fdc_id,
    f.description,
    MAX(CASE WHEN fn.nutrient_id =203 THEN fn.amount END) AS protein_g,
    MAX(CASE WHEN fn.nutrient_id = 204 THEN fn.amount END) AS fat_g,
    MAX(CASE WHEN fn.nutrient_id = 205 THEN fn.amount END) AS carbohydrate_g,
    MAX(CASE WHEN fn.nutrient_id = 208 THEN fn.amount END) AS energy_kcal,
    MAX(CASE WHEN fn.nutrient_id = 269 THEN FN.AMOUNT END) AS sugars_g,
    MAX(CASE WHEN fn.nutrient_id = 307 THEN fn.amount END) AS sodium_mg
FROM food f  
LEFT JOIN food_nutrient fn 
    ON f.fdc_id = fn.fdc_id 
    AND fn.nutrient_id IN (203, 204, 205, 208, 269, 307)
GROUP BY 
    f.fdc_id, 
    f.description;

CREATE TABLE ingredient_mapping (
    recipe_ingredient_name TEXT PRIMARY KEY,
    matched_fdc_id INTEGER,
    matched_food_name TEXT,
    match_status TEXT,
    notes TEXT,
    FOREIGN KEY (matched_fdc_id) REFERENCES food(fdc_id)
);
INSERT INTO ingredient_mapping (
    recipe_ingredient_name,
    matched_fdc_id,
    matched_food_name,
    match_status,
    notes
)
SELECT DISTINCT
    ingredient_name,
    NULL,
    NULL,
    'unmatched',
    NULL
FROM ingredients_master;