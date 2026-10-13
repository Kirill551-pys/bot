import os
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')

# 🔥 Обновленный список возможных названий колонок с коэффициентами
ODDS_PATTERNS = {
    'result': [
        ['PSCH', 'PSCD', 'PSCA'],          # Вариант 1: Pinnacle
        ['OddHome', 'OddDraw', 'OddAway'], # Вариант 2: Твой формат (как в Champions League)
        ['B365H', 'B365D', 'B365A'],       # Вариант 3: Bet365
        ['WHH', 'WHD', 'WHA']              # Вариант 4: William Hill
    ],
    'total': [
        ['PSCOver', 'PSCUnder'],           # Вариант 1
        ['Over25', 'Under25'],             # Вариант 2: Твой формат
        ['B365>2.5', 'B365<2.5']           # Вариант 3
    ]
}

def check_league(league_folder):
    """Проверяет одну лигу на наличие колонок с коэффициентами"""
    csv_path = os.path.join(DATA_DIR, league_folder, 'matches.csv')
    
    if not os.path.exists(csv_path):
        return None
    
    try:
        # Читаем только заголовки и пару строк для скорости и избежания ошибок парсинга
        df = pd.read_csv(csv_path, nrows=5, on_bad_lines='skip')
        columns = df.columns.tolist()
        
        # Ищем совпадения для исходов
        result_cols_found = []
        for pattern in ODDS_PATTERNS['result']:
            if all(col in columns for col in pattern):
                result_cols_found = pattern
                break
                
        # Ищем совпадения для тоталов
        total_cols_found = []
        for pattern in ODDS_PATTERNS['total']:
            if all(col in columns for col in pattern):
                total_cols_found = pattern
                break
        
        # Подсчет общего числа матчей (быстрый способ)
        try:
            total_matches = sum(1 for line in open(csv_path, 'r', encoding='utf-8') if line.strip()) - 1
        except:
            total_matches = "N/A"

        return {
            'league': league_folder,
            'total_matches': total_matches,
            'has_result_odds': len(result_cols_found) > 0,
            'has_total_odds': len(total_cols_found) > 0,
            'result_cols': result_cols_found,
            'total_cols': total_cols_found,
        }
    
    except Exception as e:
        return {'league': league_folder, 'error': str(e)}

def main():
    print("=" * 80)
    print("🔍 ПРОВЕРКА НАЛИЧИЯ КОЛОНОК С КОЭФФИЦИЕНТАМИ (УМНЫЙ ПОИСК)")
    print("=" * 80)
    
    leagues_with_result = []
    leagues_with_total = []
    
    for league_folder in sorted(os.listdir(DATA_DIR)):
        league_path = os.path.join(DATA_DIR, league_folder)
        if not os.path.isdir(league_path):
            continue
        
        result = check_league(league_folder)
        
        if result is None:
            print(f"\n❌ {league_folder}: CSV не найден")
            continue
        
        if 'error' in result:
            print(f"\n❌ {league_folder}: Ошибка чтения - {result['error']}")
            continue
        
        print(f"\n📊 {league_folder.upper()} (~{result['total_matches']} строк):")
        
        if result['has_result_odds']:
            print(f"   ✅ Исходы 1X2: найдены как {', '.join(result['result_cols'])}")
            leagues_with_result.append(league_folder)
        else:
            print(f"   ❌ Исходы 1X2: не найдены известные паттерны")
        
        if result['has_total_odds']:
            print(f"   ✅ Тотал 2.5: найден как {', '.join(result['total_cols'])}")
            leagues_with_total.append(league_folder)
        else:
            print(f"   ❌ Тотал 2.5: не найдены известные паттерны")
    
    print("\n" + "=" * 80)
    print("📈 ИТОГОВАЯ СТАТИСТИКА")
    print("=" * 80)
    print(f"✅ Лиг с коэффициентами на исходы (1X2): {len(leagues_with_result)}")
    print(f"✅ Лиг с коэффициентами на тотал 2.5: {len(leagues_with_total)}")
    
    # Лиги, где есть И то, и другое (идеально для Stage 2)
    perfect_matches = set(leagues_with_result) & set(leagues_with_total)
    print(f"\n🎯 ИДЕАЛЬНЫЕ КАНДИДАТЫ для Stage 2 (есть и 1X2, и Тотал): {len(perfect_matches)} лиг")
    for lm in sorted(list(perfect_matches)):
        print(f"   ➕ {lm}")

if __name__ == '__main__':
    main()