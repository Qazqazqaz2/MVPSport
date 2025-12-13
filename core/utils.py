import sys
import math
import socket
import re
from datetime import datetime, timedelta


def create_bracket(wrestlers, category_name, bracket_type=None):
    """
    Создаёт турнирную сетку для категории.

    :param wrestlers: список участников (dict с ключами как минимум "name")
    :param category_name: название категории
    :param bracket_type: если 'round_robin', принудительно создаётся круговая система.
                         Если None, то до 5 участников — круговая, иначе олимпийка.
    """
    # Определяем тип сетки
    if bracket_type is None:
        bracket_type = "round_robin" if len(wrestlers) <= 5 else "elimination"

    bracket = {
        "participants": wrestlers,
        "matches": [],
        "type": bracket_type,
        "num_participants": len(wrestlers),
    }

    # Круговая система
    if bracket["type"] == "round_robin":
        # Фильтруем участников, убирая ПРОПУСК
        real_wrestlers = [w for w in wrestlers if w.get("name", "") != "ПРОПУСК"]
        n = len(real_wrestlers)
        
        if n < 2:
            return bracket
        
        # Создаём матчи с правильной организацией по раундам для максимального отдыха
        # Используем алгоритм round-robin tournament scheduling
        matches_by_round = {}
        
        # Если нечётное количество участников, добавляем фиктивного для алгоритма
        is_odd = n % 2 == 1
        if is_odd:
            participants_list = real_wrestlers + [{"name": "ПРОПУСК"}]
            n_working = n + 1
        else:
            participants_list = real_wrestlers
            n_working = n
        
        # Количество раундов = n-1 (или n если нечётное)
        num_rounds = n_working - 1
        
        # Алгоритм round-robin: фиксируем первого участника, остальные вращаются
        for round_num in range(1, num_rounds + 1):
            matches_by_round[round_num] = []
            
            # В каждом раунде первый участник играет с последним,
            # второй с предпоследним и т.д.
            for i in range(n_working // 2):
                idx1 = i
                idx2 = n_working - 1 - i
                
                w1 = participants_list[idx1]
                w2 = participants_list[idx2]
                
                # Пропускаем матчи с ПРОПУСК
                if w1["name"] == "ПРОПУСК" or w2["name"] == "ПРОПУСК":
                    continue
                
                match = {
                    "id": f"{category_name}_R{round_num}_M{len(matches_by_round[round_num]) + 1}",
                    "wrestler1": w1["name"],
                    "wrestler2": w2["name"],
                    "club1": w1.get("club", ""),
                    "club2": w2.get("club", ""),
                    "completed": False,
                    "score1": 0,
                    "score2": 0,
                    "winner": None,
                    "round": round_num,
                }
                matches_by_round[round_num].append(match)
            
            # Вращаем список участников (кроме первого)
            # Последний участник становится вторым, остальные сдвигаются
            if round_num < num_rounds:
                # Сохраняем первого
                first = participants_list[0]
                # Сохраняем последнего
                last = participants_list[-1]
                # Сдвигаем всех кроме первого на одну позицию вправо
                for i in range(n_working - 1, 1, -1):
                    participants_list[i] = participants_list[i - 1]
                # Вставляем последнего на вторую позицию
                participants_list[1] = last
        
        # Собираем все матчи в один список
        for round_num in sorted(matches_by_round.keys()):
            bracket["matches"].extend(matches_by_round[round_num])
        
        return bracket

    # Олимпийская система
    sorted_wrestlers = sorted(
        wrestlers,
        key=lambda w: (
            w.get("rank", "Нет") != "Нет",
            w.get("rank", ""),
            w.get("name", ""),
        ),
        reverse=True,
    )

    # Убираем "ПРОПУСК" из списка участников
    real_wrestlers = [w for w in sorted_wrestlers if w["name"] != "ПРОПУСК"]

    # Если участников нет — возвращаем пустую сетку
    if not real_wrestlers:
        return {
            "participants": real_wrestlers,
            "matches": [],
            "type": "elimination",
            "num_participants": 0,
        }

    # Вычисляем ближайшую степень двойки
    bracket_size = 1
    while bracket_size < len(real_wrestlers):
        bracket_size *= 2

    # Добавляем "ПРОПУСК" только для заполнения сетки
    padded_wrestlers = real_wrestlers[:]
    while len(padded_wrestlers) < bracket_size:
        padded_wrestlers.append({"name": "ПРОПУСК", "club": "", "rank": "", "weight": 0})

    # Создаём матчи первого раунда
    matches = []
    for i in range(0, len(padded_wrestlers), 2):
        w1 = padded_wrestlers[i]
        w2 = padded_wrestlers[i + 1]

        # Пропускаем матчи, где оба — ПРОПУСК (на всякий случай)
        if w1["name"] == "ПРОПУСК" and w2["name"] == "ПРОПУСК":
            continue

        match = {
            "id": f"{category_name}_R1_M{i // 2 + 1}",
            "wrestler1": w1["name"],
            "wrestler2": w2["name"],
            "club1": w1.get("club", ""),
            "club2": w2.get("club", ""),
            "completed": False,
            "score1": 0,
            "score2": 0,
            "winner": None,
            "round": 1,
        }
        matches.append(match)

    bracket["matches"] = matches
    return bracket

def generate_schedule(tournament_data, start_time="10:00", match_duration=8, n_mats=3):
    """
    Формирует расписание матчей для всех категорий турнира в формате как на фото.
    Распределяет матчи равномерно по коврам и номерам схваток.
    Сортирует категории по весу (от меньшей к большей).
    """
    # Убеждаемся, что n_mats - это целое число и минимум 1
    try:
        n_mats = int(n_mats)
    except (ValueError, TypeError):
        n_mats = 2
    if n_mats < 1:
        n_mats = 2
        print(f"[WARNING generate_schedule] n_mats было меньше 1, установлено значение {n_mats}")
    
    # Предпочитаемый ковёр для назначения категорий, если задан в настройках сети
    # ВАЖНО: всегда перезагружаем настройки перед чтением, чтобы получить актуальное значение
    preferred_mat_index = None
    try:
        from core.settings import get_settings
        settings = get_settings()
        settings.load_settings()  # Принудительно перезагружаем настройки
        preferred_mat = settings.get("network", "mat_number", 1)
        # Преобразуем в int, обрабатывая случаи когда значение может быть строкой
        try:
            preferred_mat = int(preferred_mat)
        except (ValueError, TypeError):
            preferred_mat = 1
        preferred_mat_index = preferred_mat - 1
        if preferred_mat_index < 0 or preferred_mat_index >= n_mats:
            preferred_mat_index = None
        print(f"[DEBUG generate_schedule] Прочитан preferred_mat={preferred_mat} из настроек, preferred_mat_index={preferred_mat_index}, n_mats={n_mats}")
    except Exception as e:
        print(f"[WARNING generate_schedule] Не удалось получить предпочитаемый ковёр из настроек: {e}")
        preferred_mat_index = None

    print(f"[DEBUG generate_schedule] Начало генерации расписания, n_mats={n_mats} (тип: {type(n_mats).__name__}), preferred_mat_index={preferred_mat_index}")
    schedule = []
    
    # Функция для извлечения веса из названия категории
    def extract_weight(category_name):
        """Извлекает вес из названия категории (например, '22 кг' -> 22, '28 кг №2' -> 28)"""
        # Ищем число в начале названия категории
        match = re.search(r'(\d+)', str(category_name))
        if match:
            return int(match.group(1))
        return 9999  # Если не найдено, ставим в конец
    
    # Сортируем категории по весу (от меньшей к большей)
    categories_sorted = sorted(
        tournament_data["categories"].items(),
        key=lambda x: extract_weight(x[0])
    )
    
    # Подготовим быстрый поиск участников по имени (игнорируем пустые имена)
    participants = [
        p for p in tournament_data.get("participants", [])
        if isinstance(p, dict) and p.get("name") and str(p.get("name")).strip()
    ]
    participant_by_name = {str(p["name"]).strip(): p for p in participants}

    # Собираем все матчи из всех категорий в отсортированном порядке
    all_matches = []
    for category_name, cat_data in categories_sorted:
        for match in cat_data.get("matches", []):
            # Получаем имена участников из матча (это уже должно быть полное name)
            w1_name = match.get("wrestler1", "")
            w2_name = match.get("wrestler2", "")
            
            # Ищем полные данные участников (name) из списка участников турнира
            # Используем точное совпадение по имени, игнорируя пустые строки
            if w1_name in participant_by_name:
                w1_name = participant_by_name[w1_name]["name"]
            if w2_name in participant_by_name:
                w2_name = participant_by_name[w2_name]["name"]
            
            # Получаем клубы/цвета участников
            club1 = match.get("club1", "")
            club2 = match.get("club2", "")
            color1 = match.get("color1", "")
            color2 = match.get("color2", "")
            
            # Если клубы не указаны в матче, ищем их в участниках
            if not club1 or not club2:
                for participant in participants:
                    if participant.get("name") == w1_name:
                        club1 = participant.get("club", club1)
                        color1 = participant.get("color", color1)
                    if participant.get("name") == w2_name:
                        club2 = participant.get("club", club2)
                        color2 = participant.get("color", color2)
            
            all_matches.append({
                "category": category_name,
                "wrestler1": w1_name,  # Полное имя (name) участника
                "wrestler2": w2_name,  # Полное имя (name) участника
                "club1": club1,
                "club2": club2,
                "match_id": match["id"],
                "color1": color1,
                "color2": color2
            })
    
    if not all_matches:
        return schedule
    
    # Группируем матчи по категориям
    matches_by_category = {}
    for match in all_matches:
        category = match["category"]
        if category not in matches_by_category:
            matches_by_category[category] = []
        matches_by_category[category].append(match)
    
    # Распределяем категории по коврам (каждая категория целиком на одном ковре)
    # Сортируем категории по весу для сохранения порядка
    categories_list = sorted(
        matches_by_category.keys(),
        key=lambda cat: extract_weight(cat)
    )
    
    # Используем жадный алгоритм для балансировки нагрузки:
    # категорию с большим количеством матчей размещаем на ковре с наименьшим количеством матчей
    categories_per_mat = [[] for _ in range(n_mats)]
    mat_match_counts = [0] * n_mats  # Счетчики матчей на каждом ковре
    
    # Сортируем категории по количеству матчей (от большего к меньшему) для лучшего распределения
    categories_with_counts = [(cat, len(matches_by_category[cat])) for cat in categories_list]
    categories_with_counts.sort(key=lambda x: x[1], reverse=True)
    
    # Распределяем категории по коврам
    print(f"[DEBUG generate_schedule] n_mats={n_mats} (тип: {type(n_mats).__name__}), категорий: {len(categories_with_counts)}")
    print(f"[DEBUG generate_schedule] categories_per_mat имеет {len(categories_per_mat)} элементов")
    print(f"[DEBUG generate_schedule] mat_match_counts имеет {len(mat_match_counts)} элементов")
    
    if n_mats == 0:
        print(f"[ERROR generate_schedule] n_mats равен 0! Исправляем на 2")
        n_mats = 2
        categories_per_mat = [[] for _ in range(n_mats)]
        mat_match_counts = [0] * n_mats
    
    # Распределяем категории по коврам с чередованием для равномерного распределения
    for idx, (category, match_count) in enumerate(categories_with_counts):
        if n_mats > 0:
            # Находим все ковры с минимальным количеством матчей
            min_count = min(mat_match_counts)
            mats_with_min_count = [i for i in range(n_mats) if mat_match_counts[i] == min_count]
            
            # Если среди ковров с минимальной нагрузкой есть предпочитаемый ковёр — используем его
            if preferred_mat_index is not None and preferred_mat_index in mats_with_min_count:
                mat_index = preferred_mat_index
            else:
                # Чередуем между коврами с минимальной нагрузкой
                mat_index = mats_with_min_count[idx % len(mats_with_min_count)]
            
            print(f"[DEBUG generate_schedule] Категория '{category}' ({match_count} матчей): мин.счётчик={min_count}, ковры с мин.счётчиком={mats_with_min_count}, выбран ковёр {mat_index + 1} (индекс {mat_index}), preferred={preferred_mat_index}")
        else:
            mat_index = 0
        # Назначаем категорию на этот ковёр
        categories_per_mat[mat_index].append(category)
        # Обновляем счётчик матчей на ковре
        mat_match_counts[mat_index] += match_count
        print(f"[DEBUG generate_schedule] После назначения: счётчики матчей по коврам = {mat_match_counts}")
    
    print(f"[DEBUG generate_schedule] Распределение по коврам: {[len(cats) for cats in categories_per_mat]}")
    print(f"[DEBUG generate_schedule] Матчей по коврам: {mat_match_counts}")
    if len(categories_per_mat) > 0:
        print(f"[DEBUG generate_schedule] Категории на ковре 1: {categories_per_mat[0]}")
    if len(categories_per_mat) > 1:
        print(f"[DEBUG generate_schedule] Категории на ковре 2: {categories_per_mat[1]}")
    
    # Генерируем расписание: для каждого ковра распределяем матчи его категорий по времени
    # Матчи разных категорий на одном ковре чередуются по порядку для отдыха участников
    for mat_index in range(n_mats):
        print(f"[DEBUG generate_schedule] Обработка ковра {mat_index + 1} (индекс {mat_index}), категорий на ковре: {len(categories_per_mat[mat_index])}")
        if len(categories_per_mat[mat_index]) == 0:
            print(f"[DEBUG generate_schedule] На ковре {mat_index + 1} нет категорий, пропускаем")
            continue
        current_time = datetime.strptime(start_time, "%H:%M")
        
        # Собираем все матчи всех категорий этого ковра с их раундами
        mat_matches_by_category = {}
        for category in categories_per_mat[mat_index]:
            print(f"[DEBUG generate_schedule] Обработка категории '{category}' на ковре {mat_index + 1}")
            matches = matches_by_category[category]
            cat_data = tournament_data["categories"].get(category, {})
            cat_matches = cat_data.get("matches", [])
            
            # Создаем список матчей с раундами
            category_matches = []
            for idx, match in enumerate(matches):
                # Ищем исходный матч в категории для получения правильного раунда
                match_round = idx + 1  # По умолчанию
                for cat_match in cat_matches:
                    if cat_match.get("id") == match["match_id"]:
                        match_round = cat_match.get("round", idx + 1)
                        break
                
                category_matches.append({
                    "match": match,
                    "round": match_round,
                    "index": idx  # Индекс в списке матчей категории
                })
            
            mat_matches_by_category[category] = category_matches
        
        # Чередуем матчи разных категорий по порядку (первый матч каждой категории, затем второй и т.д.)
        # Находим максимальное количество матчей среди всех категорий на этом ковре
        max_matches = 0
        for category_matches in mat_matches_by_category.values():
            max_matches = max(max_matches, len(category_matches))
        
        # Распределяем матчи, чередуя категории
        for match_index in range(max_matches):
            # Для каждого индекса собираем матчи из всех категорий
            round_matches = []
            for category, category_matches in mat_matches_by_category.items():
                # Берем матч с нужным индексом, если он есть
                if match_index < len(category_matches):
                    match_info = category_matches[match_index]
                    round_matches.append({
                        "category": category,
                        "match": match_info["match"],
                        "round": match_info["round"]
                    })
            
            # Сортируем матчи по категории для стабильного порядка
            round_matches.sort(key=lambda x: x["category"])
            
            # Добавляем матчи в расписание
            for match_info in round_matches:
                match = match_info["match"]
                mat_number = mat_index + 1
                schedule_item = {
                    "time": current_time.strftime("%H:%M"),
                    "mat": mat_number,
                    "category": match["category"],
                    "wrestler1": match["wrestler1"],
                    "wrestler2": match["wrestler2"],
                    "club1": match.get("club1", ""),
                    "club2": match.get("club2", ""),
                    "match_id": match["match_id"],
                    "round": match_info["round"]
                }
                schedule.append(schedule_item)
                if len(schedule) <= 5:  # Выводим только первые 5 для отладки
                    print(f"[DEBUG generate_schedule] Добавлен матч #{len(schedule)}: категория '{match['category']}', ковёр {mat_number} (mat_index={mat_index}), время {schedule_item['time']}")
                
                # Увеличиваем время для следующего матча
                current_time += timedelta(minutes=match_duration)
    
    # Отладочная информация о результате
    mats_in_result = {}
    for item in schedule:
        mat = item.get("mat")
        mats_in_result[mat] = mats_in_result.get(mat, 0) + 1
    print(f"[DEBUG generate_schedule] Результат: всего {len(schedule)} матчей, распределение по коврам: {mats_in_result}")
    
    # Сортируем расписание по весу категории, затем по времени и ковру
    # Это гарантирует, что категории идут от меньшей к большей
    schedule.sort(key=lambda x: (
        extract_weight(x["category"]),  # Сначала по весу категории
        x["time"],  # Затем по времени
        x["mat"]  # Затем по ковру
    ))
    
    # Сохраняем в данные турнира
    tournament_data["schedule"] = schedule
    return schedule

def get_local_ip():
    """Получение локального IP адреса"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"

def get_wrestler_club(tournament_data, wrestler_name):
    """Находит клуб борца по имени в данных турнира"""
    if not tournament_data or 'participants' not in tournament_data:
        return ""
    
    for participant in tournament_data['participants']:
        if participant.get('name') == wrestler_name:
            return participant.get('club', '')
    return ""