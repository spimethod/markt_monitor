import os
import psycopg2
from psycopg2.extras import RealDictCursor

# === Параметры подключения к PostgreSQL (Railway) ===
PGHOST = os.getenv("PGHOST")
PGPORT = os.getenv("PGPORT", "5432")
PGUSER = os.getenv("PGUSER")
PGPASSWORD = os.getenv("PGPASSWORD")
PGDATABASE = os.getenv("PGDATABASE")

def check_table_structure():
    """Проверяет структуру таблицы markets"""
    conn = None
    try:
        # Проверяем наличие переменных окружения
        if not all([PGHOST, PGUSER, PGPASSWORD, PGDATABASE]):
            print("❌ Не все переменные окружения для PostgreSQL настроены:")
            print(f"   PGHOST: {'✅' if PGHOST else '❌'}")
            print(f"   PGUSER: {'✅' if PGUSER else '❌'}")
            print(f"   PGPASSWORD: {'✅' if PGPASSWORD else '❌'}")
            print(f"   PGDATABASE: {'✅' if PGDATABASE else '❌'}")
            return
        
        print("🔗 Подключаюсь к PostgreSQL на Railway...")
        conn = psycopg2.connect(
            host=PGHOST,
            port=PGPORT,
            user=PGUSER,
            password=PGPASSWORD,
            database=PGDATABASE
        )
        
        print("✅ Подключение успешно!")
        
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            # Получаем информацию о структуре таблицы
            cursor.execute("""
                SELECT column_name, data_type, is_nullable, column_default
                FROM information_schema.columns 
                WHERE table_name = 'markets'
                ORDER BY ordinal_position;
            """)
            
            columns = cursor.fetchall()
            
            if not columns:
                print("❌ Таблица 'markets' не найдена!")
                return
            
            print("📊 Структура таблицы 'markets':")
            print("=" * 80)
            print(f"{'Колонка':<20} {'Тип':<15} {'NULL':<8} {'По умолчанию'}")
            print("-" * 80)
            
            for col in columns:
                nullable = "YES" if col['is_nullable'] == 'YES' else "NO"
                default = col['column_default'] or "NULL"
                print(f"{col['column_name']:<20} {col['data_type']:<15} {nullable:<8} {default}")
            
            print("=" * 80)
            
            # Проверяем количество записей
            cursor.execute("SELECT COUNT(*) as count FROM markets")
            count = cursor.fetchone()['count']
            print(f"📈 Всего записей в таблице: {count}")
            
            # Проверяем статусы рынков
            cursor.execute("""
                SELECT market_status, COUNT(*) as count 
                FROM markets 
                GROUP BY market_status 
                ORDER BY count DESC;
            """)
            
            statuses = cursor.fetchall()
            print(f"\n📊 Статистика по статусам:")
            for status in statuses:
                print(f"   {status['market_status']}: {status['count']}")
            
            # Показываем последние 3 записи
            cursor.execute("""
                SELECT id, question, slug, market_status, created_at, trading_activated_at
                FROM markets 
                ORDER BY created_at DESC 
                LIMIT 3;
            """)
            
            recent = cursor.fetchall()
            print(f"\n🆕 Последние 3 записи:")
            for record in recent:
                print(f"   ID: {record['id']}, Slug: {record['slug']}, Status: {record['market_status']}")
                print(f"   Created: {record['created_at']}, Activated: {record['trading_activated_at']}")
                print()
            
    except psycopg2.OperationalError as e:
        print(f"❌ Ошибка подключения к PostgreSQL: {e}")
        print("💡 Убедитесь, что переменные окружения настроены правильно")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    check_table_structure() 