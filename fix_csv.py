import csv
import os
import glob

def fix_single_csv(input_path):
    """Исправляет один CSV-файл, выравнивая количество колонок"""
    print(f"🔧 Обрабатываю: {os.path.basename(input_path)}")
    
    # 1. Читаем все строки и находим максимальное количество колонок
    valid_lines = []
    max_cols = 0
    
    try:
        with open(input_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue # Пропускаем полностью пустые строки
                
                # Пропускаем явный мусор (строки без запятых или слишком короткие)
                if line.count(',') < 5:
                    continue 
                
                cols = line.split(',')
                if len(cols) > max_cols:
                    max_cols = len(cols)
                valid_lines.append(cols)
                
    except Exception as e:
        print(f"   ❌ Ошибка чтения: {e}")
        return

    if not valid_lines:
        print("   ⚠️ Файл пуст или не содержит валидных данных")
        return

    # 2. Перезаписываем файл с единым количеством колонок
    with open(input_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        for cols in valid_lines:
            # Если в этой строке колонок меньше, чем максимум, добавляем пустые
            while len(cols) < max_cols:
                cols.append('')
            writer.writerow(cols)
            
    print(f"   ✅ Успешно! Строк сохранено: {len(valid_lines)}, Колонок: {max_cols}")

def fix_all_leagues():
    """Находит все matches.csv в папке data и исправляет их"""
    data_dir = os.path.join(os.path.dirname(__file__), 'data')
    
    # Ищем все файлы matches.csv во всех подпапках
    csv_files = glob.glob(os.path.join(data_dir, '*', 'matches.csv'))
    
    print(f"🚀 Найдено файлов для обработки: {len(csv_files)}\n")
    
    for file_path in csv_files:
        fix_single_csv(file_path)
        
    print("\n🎉 ВСЕ ФАЙЛЫ УСПЕШНО ИСПРАВЛЕНЫ! Теперь можешь запускать python main.py")

if __name__ == '__main__':
    fix_all_leagues()