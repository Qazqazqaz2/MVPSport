import pandas as pd
import json
import re
from datetime import datetime
from pathlib import Path
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                             QGroupBox, QLineEdit, QTableWidget, QTableWidgetItem,
                             QFileDialog, QMessageBox, QProgressBar, QGridLayout,
                             QHeaderView, QCheckBox, QDialog, QFormLayout,
                             QComboBox, QDialogButtonBox, QInputDialog)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QBrush, QColor
from core.utils import create_bracket, generate_schedule
from core.settings import get_settings
from ui.widgets.tournament_manager import TournamentManager
import math

class ColumnMappingDialog(QDialog):
    """Простое окно сопоставления колонок с полями участников."""

    def __init__(self, columns, parent=None, suggested=None):
        super().__init__(parent)
        self.setWindowTitle("Сопоставление колонок")
        self.columns = ["—"] + list(columns)
        self.suggested = suggested or {}
        self.combos = {}

        form = QFormLayout(self)

        self.fields_config = [
            ("name", "ФИО (если одной строкой)", False),
            ("last_name", "Фамилия", False),
            ("first_name", "Имя", False),
            ("weight", "Вес", True),
            ("age", "Возраст (числом)", False),
            ("age_text", "Возраст (строкой/дата)", False),
            ("gender", "Пол", False),
            ("city", "Город", False),
            ("club", "Клуб", False),
            ("coach", "Тренер", False),
            ("experience", "Стаж/разряд", False),
        ]

        for key, label, _ in self.fields_config:
            combo = QComboBox()
            combo.addItems(self.columns)
            if key in self.suggested and self.suggested[key] in self.columns:
                combo.setCurrentText(self.suggested[key])
            self.combos[key] = combo
            form.addRow(label + ":", combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.validate_and_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def get_mapping(self):
        return {
            key: combo.currentText() if combo.currentText() != "—" else None
            for key, combo in self.combos.items()
        }

    def validate_and_accept(self):
        mapping = self.get_mapping()
        # Нужно либо поле name, либо пара last/first, а также вес
        has_name = mapping.get("name")
        has_split_name = mapping.get("last_name") or mapping.get("first_name")
        if not has_name and not has_split_name:
            QMessageBox.warning(self, "Внимание", "Укажите хотя бы ФИО или Фамилию/Имя.")
            return
        if not mapping.get("weight"):
            QMessageBox.warning(self, "Внимание", "Поле веса обязательно.")
            return
        self.accept()


class ExcelImporter(QWidget):
    def __init__(self, parent=None, network_manager=None):
        super().__init__(parent)
        self.tournament_data = None
        self.categories = {}
        self.network_manager = network_manager
        self.category_definitions = {
            'U12 М 30-35 кг': {'gender': 'М', 'age_min': 10, 'age_max': 12, 'weight_min': 30, 'weight_max': 35},
        }
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Информация о турнире
        tournament_group = QGroupBox("Информация о турнире")
        tournament_layout = QGridLayout(tournament_group)
        
        tournament_layout.addWidget(QLabel("Название турнира:"), 0, 0)
        self.tournament_name = QLineEdit("")
        tournament_layout.addWidget(self.tournament_name, 0, 1)
        
        tournament_layout.addWidget(QLabel("Дата проведения:"), 1, 0)
        self.tournament_date = QLineEdit(datetime.now().strftime("%d.%m.%Y"))
        tournament_layout.addWidget(self.tournament_date, 1, 1)
        
        tournament_layout.addWidget(QLabel("Место проведения:"), 2, 0)
        self.tournament_location = QLineEdit("")
        tournament_layout.addWidget(self.tournament_location, 2, 1)
        
        layout.addWidget(tournament_group)
        
        # Загрузка файла
        load_group = QGroupBox("Загрузка файла участников (Excel / CSV)")
        load_layout = QHBoxLayout(load_group)
        
        load_btn = QPushButton("Выбрать файл")
        load_btn.clicked.connect(self.load_excel)
        load_layout.addWidget(load_btn)
        
        self.file_label = QLabel("Файл не выбран")
        load_layout.addWidget(self.file_label)
        
        layout.addWidget(load_group)
        
        # Превью данных
        layout.addWidget(QLabel("Предпросмотр данных:"))
        self.preview_table = QTableWidget()
        layout.addWidget(self.preview_table)

        # Переключатель автоматического формирования категорий по пустым строкам
        self.use_group_by_empty_rows = QCheckBox(
            "Автоматически формировать категории по группам,\n"
            "разделённым пустыми строками (название = средний вес группы)"
        )
        self.use_group_by_empty_rows.setChecked(True)
        layout.addWidget(self.use_group_by_empty_rows)
        
        # Кнопка формирования турнира
        generate_btn = QPushButton("Сформировать турнирную сетку")
        generate_btn.clicked.connect(self.generate_tournament)
        layout.addWidget(generate_btn)
        
        # Прогресс
        self.progress_bar = QProgressBar()
        layout.addWidget(self.progress_bar)
    
    def load_excel(self):
        """
        Загрузка файла с участниками.
        Поддерживаются:
        - Excel (.xlsx, .xls) с заголовками столбцов
        - Excel/CSV без заголовков: Фамилия, Имя, Возраст, Вес, Стаж, Тренер
        """
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите файл с участниками",
            "",
            "Таблицы (*.xlsx *.xls *.csv *.json)",
        )
        if not filename:
            return

        self.file_label.setText(filename)
        try:
            suffix = Path(filename).suffix.lower()

            if suffix in [".xlsx", ".xls"]:
                df_raw = self._read_excel_with_sheet_choice(filename)
                df_raw.columns = [str(c) for c in df_raw.columns]
                self.show_preview(df_raw)
                known_headers = {'Номер', 'ФИО', 'Дата рождения', 'Вес', 'Разряд', 'Пол', 'Дисциплина', 'Город', 'Клуб', 'Тренер'}
                if any(str(col).strip() in known_headers for col in df_raw.columns):
                    df = self.process_excel_data(df_raw)
                else:
                    mapped_df = self._manual_map_dataframe(df_raw)
                    if mapped_df is not None:
                        df = mapped_df
                    else:
                        df_raw = pd.read_excel(filename, header=None)
                        df_raw.columns = ["last_name", "first_name", "age_text", "weight_text", "experience_text", "coach"]
                        self.show_preview(df_raw)
                        df = self.process_csv_data(df_raw)
            elif suffix == ".csv":
                # Пробуем разные кодировки
                df_raw = None
                for encoding in ["utf-8-sig", "utf-8", "cp1251", "windows-1251"]:
                    try:
                        df_raw = pd.read_csv(
                            filename,
                            header=None,
                            encoding=encoding,
                            keep_default_na=False,
                            dtype=str  # Читаем все колонки как строки, чтобы избежать проблем с типами
                        )
                        break
                    except:
                        continue
                
                if df_raw is None:
                    QMessageBox.critical(self, "Ошибка", "Не удалось прочитать CSV файл")
                    return
                
                num_cols = df_raw.shape[1]
                if num_cols == 4:
                    df_raw.columns = ["last_name", "first_name", "extra", "weight_text"]
                elif num_cols == 6:
                    df_raw.columns = ["last_name", "first_name", "age_text", "weight_text", "experience_text", "coach"]
                else:
                    if num_cols >= 4:
                        df_raw.columns = ["last_name", "first_name", "age_text", "weight_text"] + [f"col_{i}" for i in range(4, num_cols)]
                    else:
                        QMessageBox.critical(self, "Ошибка", f"Неожиданное количество столбцов: {num_cols}")
                        return
                
                self.show_preview(df_raw)
                mapped_df = self._manual_map_dataframe(df_raw)
                if mapped_df is not None:
                    df = mapped_df
                else:
                    df = self.process_csv_data(df_raw)
            elif suffix == ".json":
                self.load_tournament_json(filename)
                return
            else:
                QMessageBox.critical(self, "Ошибка", "Неподдерживаемый формат файла")
                return

            # АВТОМАТИЧЕСКОЕ ФОРМИРОВАНИЕ ТУРНИРА ПОСЛЕ ЗАГРУЗКИ
            self.generate_tournament()
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось загрузить файл: {str(e)}")
    
    def _read_excel_with_sheet_choice(self, filename):
        """Если в Excel несколько листов, даём выбрать нужный."""
        try:
            xls = pd.ExcelFile(filename)
            if len(xls.sheet_names) <= 1:
                return pd.read_excel(filename)
            sheet, ok = QInputDialog.getItem(self, "Выбор листа", "Выберите лист:", xls.sheet_names, 0, False)
            if not ok:
                raise Exception("Лист не выбран")
            return pd.read_excel(filename, sheet_name=sheet)
        except Exception:
            return pd.read_excel(filename)

    def _suggest_mapping(self, df):
        """Пытаемся заранее выбрать подходящие колонки."""
        cols = {c.lower(): c for c in df.columns}
        def pick(*names):
            for name in names:
                if name.lower() in cols:
                    return cols[name.lower()]
            return None
        return {
            "name": pick("фио", "name"),
            "last_name": pick("фамилия", "surname", "last_name"),
            "first_name": pick("имя", "first_name"),
            "weight": pick("вес", "weight"),
            "age": pick("возраст", "age"),
            "age_text": pick("дата рождения", "дата", "birthday", "birth_date"),
            "gender": pick("пол", "gender"),
            "city": pick("город", "city"),
            "club": pick("клуб", "club"),
            "coach": pick("тренер", "coach"),
            "experience": pick("разряд", "стаж", "experience"),
        }

    def _manual_map_dataframe(self, df):
        """Запрос ручного сопоставления колонок. Возвращает стандартный датафрейм или None."""
        dialog = ColumnMappingDialog(df.columns, parent=self, suggested=self._suggest_mapping(df))
        if dialog.exec_() != QDialog.Accepted:
            return None

        mapping = dialog.get_mapping()
        result = pd.DataFrame()

        def get_col(key):
            col_name = mapping.get(key)
            return df[col_name] if col_name in df.columns else None

        name_col = get_col("name")
        ln_col = get_col("last_name")
        fn_col = get_col("first_name")
        if name_col is not None:
            result["name"] = name_col.astype(str).str.strip()
        else:
            ln_series = ln_col.astype(str).str.strip() if ln_col is not None else ""
            fn_series = fn_col.astype(str).str.strip() if fn_col is not None else ""
            result["name"] = (ln_series + " " + fn_series).str.strip()

        def parse_weight(text):
            if pd.isna(text) or str(text).strip() == "" or str(text).strip().lower() == "nan":
                return 0.0
            try:
                return float(text)
            except (ValueError, TypeError):
                pass
            text = str(text).replace(",", ".")
            m = re.search(r"(\d+(?:\.\d+)?)", text)
            return float(m.group(1)) if m else 0.0

        weight_col = get_col("weight")
        if weight_col is None:
            weight_col = get_col("weight_text")
        result["weight"] = weight_col.apply(parse_weight) if weight_col is not None else 0.0

        def parse_age(text):
            if pd.isna(text) or str(text).strip() == "":
                return None
            m = re.search(r"(\d+)", str(text))
            return int(m.group(1)) if m else None

        age_col = get_col("age")
        if age_col is not None:
            result["age"] = age_col.apply(parse_age)
        else:
            age_text_col = get_col("age_text")
            if age_text_col is not None:
                result["age"] = age_text_col.apply(parse_age)
            else:
                result["age"] = None

        gender_col = get_col("gender")
        if gender_col is not None:
            result["gender"] = gender_col.astype(str).str.upper().str.strip().apply(
                lambda x: 'М' if x in ['M', 'М', 'МУЖ', 'МУЖСКОЙ', 'MALE'] else
                'Ж' if x in ['F', 'Ж', 'ЖЕН', 'ЖЕНСКИЙ', 'FEMALE'] else x
            )
        else:
            result["gender"] = "М"

        for key, target in [("city", "city"), ("club", "club"), ("coach", "coach"), ("experience", "experience")]:
            col = get_col(key)
            result[target] = col.astype(str).str.strip() if col is not None else ""

        data_cols = [c for c in ["name", "weight", "age", "city", "club", "coach", "experience"] if c in result.columns]
        result = self._add_group_index_by_empty_rows(result, data_cols)
        self.tournament_data = result.to_dict("records")
        self.show_preview(result)
        return result
    
    def process_excel_data(self, df):
        # Стандартизация названий столбцов
        column_mapping = {
            'Номер': 'number',
            'ФИО': 'name',
            'Дата рождения': 'birth_date',
            'Вес': 'weight',
            'Разряд': 'rank',
            'Пол': 'gender',
            'Дисциплина': 'discipline',
            'Город': 'city',
            'Клуб': 'club',
            'Тренер': 'coach'
        }
        
        # Переименование столбцов
        for rus, eng in column_mapping.items():
            if rus in df.columns:
                df.rename(columns={rus: eng}, inplace=True)
        
        # Обработка весовых данных
        if 'weight' in df.columns:
            df['weight'] = pd.to_numeric(df['weight'], errors='coerce').fillna(0)
        
        # Обработка пола
        if 'gender' in df.columns:
            df['gender'] = df['gender'].astype(str).str.upper().str.strip()
            # Стандартизация значений пола
            df['gender'] = df['gender'].apply(lambda x: 'М' if x in ['M', 'М', 'МУЖ', 'МУЖСКОЙ', 'MALE'] else 
                                             'Ж' if x in ['F', 'Ж', 'ЖЕН', 'ЖЕНСКИЙ', 'FEMALE'] else x)
        
        # Для Excel ожидаем, что есть поле name (ФИО)
        # Если Фамилия/Имя раздельно — можно будет доработать при необходимости.

        # Если включена опция группировки по пустым строкам — пытаемся разметить группы
        if hasattr(self, "use_group_by_empty_rows") and self.use_group_by_empty_rows.isChecked():
            # Для определения "пустых" строк используем все пользовательские поля, кроме номера
            data_cols = [c for c in df.columns if c not in ('number',)]
            df = self._add_group_index_by_empty_rows(df, data_cols)

        self.tournament_data = df.to_dict('records')
        return df

    def process_csv_data(self, df):
        """
        Обработка формата CSV.
        Поддерживает:
        - Новый формат (4 колонки): Фамилия, Имя, что-то, Возраст
        - Старый формат (6 колонок): Фамилия, Имя, Возраст, Вес, Стаж, Тренер
        """
        # Определяем формат по количеству столбцов
        is_new_format = "extra" in df.columns and "weight_text" in df.columns and "age_text" not in df.columns
        
        if is_new_format:
            # Новый формат: last_name, first_name, extra, weight_text (столбец D - вес)
            data_cols = ["last_name", "first_name", "extra", "weight_text"]
            # Заполняем недостающие колонки пустыми значениями
            for col in ["age_text", "experience_text", "coach"]:
                if col not in df.columns:
                    df[col] = ""
        else:
            # Старый формат: last_name, first_name, age_text, weight_text, experience_text, coach
            data_cols = ["last_name", "first_name", "age_text", "weight_text", "experience_text", "coach"]
            if "extra" not in df.columns:
                df["extra"] = ""
        
        # Строковые поля - сначала преобразуем все в строки, чтобы избежать проблем с типами
        for col in data_cols:
            if col in df.columns:
                # Преобразуем в строку, обрабатывая NaN и числовые значения
                df[col] = df[col].astype(str).replace('nan', '').replace('None', '').str.strip()

        # Определяем группы участников по пустым строкам
        df = self._add_group_index_by_empty_rows(df, data_cols)

        # ФИО
        df["name"] = (df["last_name"] + " " + df["first_name"]).str.strip()

        # Возраст в годах (берём первое число из строки или просто число)
        def parse_age(text):
            if pd.isna(text) or str(text).strip() == "":
                return None
            m = re.search(r"(\d+)", str(text))
            return int(m.group(1)) if m else None

        # Возраст - только если есть колонка age_text
        if "age_text" in df.columns:
            df["age"] = df["age_text"].apply(parse_age)
        else:
            df["age"] = None

        # Вес — число (берём число, запятую меняем на точку)
        # В новом формате вес находится в столбце D (weight_text)
        def parse_weight(text):
            if pd.isna(text) or str(text).strip() == "" or str(text).strip().lower() == "nan":
                return 0.0
            # Если это уже число, просто возвращаем его
            try:
                return float(text)
            except (ValueError, TypeError):
                pass
            # Иначе пытаемся извлечь число из строки
            text = str(text).replace(",", ".")
            m = re.search(r"(\d+(?:\.\d+)?)", text)
            return float(m.group(1)) if m else 0.0

        if "weight_text" in df.columns:
            df["weight"] = df["weight_text"].apply(parse_weight)
        elif "extra" in df.columns:
            # Пытаемся извлечь вес из extra
            df["weight"] = df["extra"].apply(parse_weight)
        else:
            df["weight"] = 0.0

        # Стаж/опыт — оставляем как есть (для разделения категорий по опыту)
        if "experience_text" in df.columns:
            df["experience"] = df["experience_text"]
        else:
            df["experience"] = ""

        # Тренер
        if "coach" in df.columns:
            df["coach"] = df["coach"]
        else:
            df["coach"] = ""

        # Для таких фестивалей чаще всего все — мальчики, ставим 'М' по умолчанию
        df["gender"] = "М"

        # Клуб можно не указывать, но поле должно быть, чтобы расписание и табло работали
        if "club" not in df.columns:
            df["club"] = ""

        # Если тренер интерпретируется как клуб (по примеру) — присваиваем в club
        if "coach" in df.columns and df["coach"].notna().any():
            df["club"] = df["coach"]

        self.tournament_data = df.to_dict('records')
        return df

    def _add_group_index_by_empty_rows(self, df, columns):
        """
        Помечает группы участников по пустым строкам.
        Пустая строка = все указанные columns пустые/NaN.

        Возвращает датафрейм только с непустыми строками и полем group_index.
        """
        group_indices = []
        separator_rows = set()

        for idx, row in df.iterrows():
            is_empty = all(
                not str(row.get(col, "")).strip() or str(row.get(col, "")).strip() == 'nan'
                for col in columns
                if col in df.columns
            )
            if is_empty:
                separator_rows.add(idx)

        group_index = -1
        for idx, row in df.iterrows():
            if idx in separator_rows:
                continue
            if group_index == -1 or (idx - 1) in separator_rows:
                group_index += 1
            group_indices.append((idx, group_index))

        if group_indices:
            valid_indices, groups = zip(*group_indices)
            df_new = df.loc[list(valid_indices)].copy()
            df_new["group_index"] = list(groups)
            return df_new

        # Если нет групп/пустых строк — просто возвращаем копию без group_index
        return df.copy()
    
    def show_preview(self, df):
        # Показываем все строки, включая пустые
        rows = len(df)
        self.preview_table.setRowCount(rows)
        self.preview_table.setColumnCount(len(df.columns))
        self.preview_table.setHorizontalHeaderLabels([str(c) for c in df.columns.tolist()])

        for i in range(rows):
            for j, col in enumerate(df.columns):
                value = "" if pd.isna(df.iloc[i, j]) else str(df.iloc[i, j])
                item = QTableWidgetItem(value)
                # Если строка пустая, делаем её визуально заметной
                if value.strip() == "":
                    item.setBackground(QBrush(QColor(240, 240, 240)))
                self.preview_table.setItem(i, j, item)
        
        self.preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    
    def generate_tournament(self):
        if not hasattr(self, 'tournament_data') or not self.tournament_data:
            QMessageBox.warning(self, "Внимание", "Нет данных для формирования турнира")
            return
        
        # Автоматическое создание категорий на основе данных
        tournament_brackets = self.create_categories_automatically()
        
        # Сохранение турнира
        tournament_info = {
            'name': self.tournament_name.text(),
            'date': self.tournament_date.text(),
            'location': self.tournament_location.text(),
            'categories': tournament_brackets,
            'participants': self.tournament_data
        }
        
        # ГЕНЕРАЦИЯ РАСПИСАНИЯ
        try:
            settings = get_settings()
            n_mats = settings.get("tournament", "number_of_mats", 2)
            if n_mats < 1:
                n_mats = 2  # Минимум 2 ковра
                settings.set("tournament", "number_of_mats", n_mats)
                print(f"[WARNING] Количество ковров было меньше 1, установлено значение {n_mats}")
            schedule = generate_schedule(
                tournament_info,
                start_time="10:00",
                match_duration=8,
                n_mats=n_mats
            )
            tournament_info["schedule"] = schedule
            print(f"[INFO] Расписание сгенерировано для {n_mats} ковров")
        except Exception as e:
            print(f"Ошибка при генерации расписания: {e}")
            import traceback
            traceback.print_exc()
        
        # АВТОМАТИЧЕСКАЯ ПЕРЕДАЧА ДАННЫХ В МЕНЕДЖЕР ТУРНИРА
        main_window = self.window()
        if hasattr(main_window, 'set_tournament_data'):
            main_window.set_tournament_data(tournament_info)
            # АВТОМАТИЧЕСКОЕ ОТКРЫТИЕ МЕНЕДЖЕРА ТУРНИРА
            if hasattr(main_window, 'open_tournament_manager_tab'):
                main_window.open_tournament_manager_tab()
            
            QMessageBox.information(self, "Успех", "Турнирная сетка и расписание успешно сформированы!")
        
        # Дополнительно сохраняем в файл
        filename, _ = QFileDialog.getSaveFileName(self, "Сохранить турнир", "", "JSON files (*.json)")
        if filename:
            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(tournament_info, f, ensure_ascii=False, indent=2, default=str)
            except Exception as e:
                QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить файл: {str(e)}")

    def load_tournament_json(self, filename):
        """Загрузка готового турнира из JSON (как в менеджере турниров)."""
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                tournament_info = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось прочитать JSON: {e}")
            return

        if not isinstance(tournament_info, dict) or 'categories' not in tournament_info:
            QMessageBox.critical(self, "Ошибка", "Некорректный формат файла турнира")
            return

        self.tournament_data = tournament_info.get('participants', [])
        # Показываем превью участников, если есть
        if self.tournament_data:
            df_preview = pd.DataFrame(self.tournament_data)
            self.show_preview(df_preview)
        else:
            self.preview_table.setRowCount(0)
            self.preview_table.setColumnCount(0)

        main_window = self.window()
        if hasattr(main_window, 'set_tournament_data'):
            main_window.set_tournament_data(tournament_info)

            # Пытаемся найти уже открытый менеджер турнира
            tm_widget = None
            if hasattr(main_window, 'tab_widget'):
                for i in range(main_window.tab_widget.count()):
                    widget = main_window.tab_widget.widget(i)
                    if isinstance(widget, TournamentManager):
                        tm_widget = widget
                        break

            # Если менеджер не открыт — открываем его
            if tm_widget is None and hasattr(main_window, 'open_tournament_manager_tab'):
                main_window.open_tournament_manager_tab()
                # После создания находим добавленный виджет
                if hasattr(main_window, 'tab_widget'):
                    for i in range(main_window.tab_widget.count()):
                        widget = main_window.tab_widget.widget(i)
                        if isinstance(widget, TournamentManager):
                            tm_widget = widget
                            break

            # Прокидываем данные в менеджер и обновляем интерфейс
            if tm_widget:
                tm_widget.tournament_data = tournament_info
                tm_widget.tournament_label.setText(f"Загружен: {tournament_info.get('name', 'Без имени')}")
                tm_widget.update_tournament_info()
                tm_widget.update_categories_lists()
                tm_widget.generate_tournament_schedule()
                tm_widget.info_group.setVisible(True)
                tm_widget.management_group.setVisible(True)
                tm_widget.matches_group.setVisible(True)
        self.file_label.setText(filename)
        QMessageBox.information(self, "Успех", "Турнир загружен из JSON")
    
    def create_categories_automatically(self):
        """Автоматическое создание категорий на основе данных участников.

        Если включён переключатель \"Автоматически формировать категории по группам\"
        и в данных есть поле group_index (CSV с пустыми строками между группами),
        то каждая группа соответствует отдельной категории, название которой —
        средний алгебраический вес участников в группе.

        Иначе используется автоматическое разбиение по возрасту, весу и стажу.
        """

        # Если включена группировка по пустым строкам и есть group_index — используем её
        if (
            hasattr(self, "use_group_by_empty_rows")
            and self.use_group_by_empty_rows.isChecked()
            and any("group_index" in w for w in self.tournament_data)
        ):
            return self._create_categories_by_groups()

        # Иначе — старый режим: по возрасту, весу и стажу
        return self._create_categories_by_auto_params()

    def _create_categories_by_groups(self):
        """Создание категорий по группам (group_index), разделённым пустыми строками в CSV.

        Название категории = средняя арифметическая весов участников в группе,
        с округлением в большую сторону если нужно (math.ceil).
        """
        categories = {}

        # Группируем участников по group_index
        groups = {}
        for wrestler in self.tournament_data:
            g_idx = wrestler.get("group_index")
            if g_idx is None:
                continue
            groups.setdefault(g_idx, []).append(wrestler)

        name_counts = {}

        # Идём по группам в порядке их индекса
        for g_idx in sorted(groups.keys()):
            wrestlers = groups[g_idx]
            if not wrestlers:
                continue

            weights = [float(w.get("weight", 0) or 0) for w in wrestlers]
            if not weights:
                # если по какой-то причине нет весов — пропускаем группу
                continue

            avg_weight = sum(weights) / len(weights)
            # Округляем в большую сторону
            weight_class = math.ceil(avg_weight)
            base_name = f"{weight_class} кг"

            if base_name not in name_counts:
                name_counts[base_name] = 0
            name_counts[base_name] += 1

            if name_counts[base_name] > 1:
                category_name = f"{base_name} №{name_counts[base_name]}"
            else:
                category_name = base_name

            # Создаём структуру категории
            categories[category_name] = {
                "gender": wrestlers[0].get("gender", "М"),
                "age": wrestlers[0].get("age"),
                "weight_min": min(weights) if weights else 0,
                "weight_max": max(weights) if weights else 0,
                "experience": wrestlers[0].get("experience", ""),
                "participants": wrestlers,
                "matches": [],
            }

            # Создаём сетку для каждой категории: авто-выбор типа (круг если <=5, иначе олимпийка)
        for category_name, data in categories.items():
            participants = data["participants"]
            bracket = create_bracket(participants, category_name, bracket_type=None)
            categories[category_name]["matches"] = bracket["matches"]
            categories[category_name]["type"] = bracket["type"]

        return categories

    def _create_categories_by_auto_params(self):
        """Создание категорий по возрасту, весу и стажу (старый режим)."""
        categories = {}

        # Группируем участников по возрасту, весу и стажу
        for wrestler in self.tournament_data:
            gender = wrestler.get('gender', 'М')
            weight = float(wrestler.get('weight', 0) or 0)
            age = wrestler.get('age')
            experience = wrestler.get('experience', '')

            # Определяем весовую категорию
            weight_category = self.determine_weight_category(weight, gender)

            # Текст возраста
            age_text = f"{age} лет" if age is not None else "возраст не указан"

            # Название категории: пример — "6 лет, до 24кг, 1 год - 2 года"
            if experience:
                category_name = f"{age_text}, {weight_category}, {experience}"
            else:
                category_name = f"{age_text}, {weight_category}"
            
            if category_name not in categories:
                categories[category_name] = {
                    'gender': gender,
                    'age': age,
                    'weight_min': weight_category.split('-')[0] if '-' in weight_category else weight_category.replace('+', '').replace('до ', '').replace('кг', ''),
                    'weight_max': weight_category.split('-')[1] if '-' in weight_category else '999',
                    'experience': experience,
                    'participants': [],
                    'matches': []
                }
            
            categories[category_name]['participants'].append(wrestler)
        
        # Создаем матчи для каждой категории (автовыбор типа сетки)
        for category_name, data in categories.items():
            participants = data['participants']
            bracket = create_bracket(participants, category_name, bracket_type=None)
            categories[category_name]['matches'] = bracket['matches']
            categories[category_name]['type'] = bracket['type']
        
        return categories
    
    def determine_weight_category(self, weight, gender):
        """Определяет весовую категорию по весу и полу"""
        if gender == 'М':
            categories = [30, 35, 40, 45, 50, 55, 60, 66, 74, 84, 96, 120]
        else:
            categories = [28, 32, 36, 40, 44, 48, 53, 58, 63, 69, 76]
        
        for i, cat in enumerate(categories):
            if weight <= cat:
                if i == 0:
                    return f"до {cat}кг"
                else:
                    return f"{categories[i-1]}-{cat}кг"
        
        return f"{categories[-1]}+кг"