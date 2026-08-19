# PostgreSQL 설정

기본값:

```text
Database: postgres
Schema: practice
search_path: practice, public
```

`.env`에 다음을 추가합니다.

```env
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=실제_비밀번호
DB_HOST=127.0.0.1
DB_PORT=5432
DB_SCHEMA=practice
```

실행 순서:

```cmd
python manage.py prepare_postgres
python manage.py check_database_setup
python manage.py migrate
python manage.py runserver
```

샘플 `.env`에는 PostgreSQL 비밀번호가 포함되어 있지 않았으므로 비밀번호는 사용자가 로컬에서 입력해야 합니다.
