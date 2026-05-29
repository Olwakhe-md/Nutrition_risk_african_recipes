CREATE TABLE test_table (
    id INTEGER PRIMARY KEY,
    name TEXT
);
SELECT name, type
FROM sqlite_master
WHERE type IN ('table','view')
ORDER BY type, name;
CREATE TABLE food(
    fdc_id INTEGER
    description TEXT
    data_type TEXT
    food_category_id INTEGER
);
DROP TABLE test_table;
