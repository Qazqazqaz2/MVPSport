# Константы для греко-римской борьбы
PERIOD_DURATION = 180  # 3 минуты в секундах
BREAK_DURATION = 30    # 30 секунд перерыв
PERIODS = 2
TECHNICAL_SUPERIORITY = 8  # Разница для технического превосходства
CAUTION_LIMIT = 3          # 3 предупреждения приводят к дисквалификации

# Сетевые настройки
NETWORK_PORT = 12345
# Дополнительный модуль синхронизации расписаний
SCHEDULE_SYNC_PORT = 12346
SCHEDULE_SYNC_HEARTBEAT = 3  # секунды между heartbeat
SCHEDULE_SYNC_TIMEOUT = 12   # секунд до пометки узла как оффлайн