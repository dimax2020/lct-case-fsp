CREATE TABLE IF NOT EXISTS practice_vacancies (
  practice_id text NOT NULL,
  vacancy_id text NOT NULL,
  PRIMARY KEY (practice_id, vacancy_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS practice_vacancies_vacancy ON practice_vacancies (vacancy_id);
INSERT INTO practice_vacancies (practice_id, vacancy_id)
SELECT DISTINCT ON (vacancy_id) id, vacancy_id
FROM practices
WHERE vacancy_id IS NOT NULL AND btrim(vacancy_id) <> '' AND source_practice_id IS NULL
ORDER BY vacancy_id, updated_at DESC
ON CONFLICT DO NOTHING;
