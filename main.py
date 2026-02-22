import sys
import json
import os
import re
from collections import defaultdict
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QFileDialog, QLineEdit, QListWidget, QLabel,
    QMessageBox, QSplitter, QMenu, QAction, QTextBrowser
)
from PyQt5.QtCore import Qt
from striprtf.striprtf import rtf_to_text
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.corpus import stopwords
import pymorphy3

# Загрузка необходимых данных NLTK
def setup_nltk():
    try:
        nltk.data.find('tokenizers/punkt')
    except LookupError:
        nltk.download('punkt')
    
    try:
        nltk.data.find('tokenizers/punkt/russian.pickle')
    except LookupError:
        nltk.download('punkt')
    
    try:
        nltk.data.find('corpora/stopwords')
    except LookupError:
        nltk.download('stopwords')

setup_nltk()

# Загрузка стоп-слов и морфологического анализатора
russian_stopwords = set(stopwords.words('russian'))
# Расширяем стоп-слова для частиц и артефактов
russian_stopwords.update({
    'бы', 'же', 'ли', 'быть', 'нибудь', 'кое', 'то', 'либо', 'таки',
    'нибыть', 'либыть', 'тобыть', 'когда-нибудь', 'где-нибудь'
})

morph = pymorphy3.MorphAnalyzer()

class TextProcessor:
    """Обработка текста: извлечение лексем и словосочетаний с учётом границ предложений"""
    
    @staticmethod
    def read_file(filepath):
        """Чтение TXT или RTF файла"""
        ext = filepath.lower().split('.')[-1]
        if ext == 'rtf':
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                return rtf_to_text(f.read())
        elif ext == 'txt':
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        else:
            raise ValueError("Поддерживаются только .txt и .rtf файлы")
    
    @staticmethod
    def extract_collocations(text):
        """
        Извлечение лингвистически корректных словосочетаний.
        Ключевые улучшения:
        1. Обработка ТОЛЬКО внутри предложений (устранение межпредложных связей)
        2. Фильтрация частиц и артефактов («нибыть» и др.)
        3. Минимум 4 символа для лексем
        4. Только знаменательные части речи
        """
        # Разбиваем текст на предложения с поддержкой русского языка
        sentences = sent_tokenize(text.lower(), language='russian')
        colloc_dict = defaultdict(set)
        
        for sent in sentences:
            # Токенизация с сохранением дефисных слов (например, "когда-нибудь")
            words = re.findall(r'\b[а-яё]+(?:-[а-яё]+)*\b', sent)
            
            lemmas = []
            for word in words:
                # Пропускаем короткие слова и стоп-слова
                if len(word) < 4 or word in russian_stopwords:
                    continue
                
                # Морфологический анализ
                parses = morph.parse(word)
                if not parses:
                    continue
                
                # Выбираем самый вероятный разбор
                parsed = max(parses, key=lambda p: p.score)
                pos = parsed.tag.POS
                lemma = parsed.normal_form.lower()
                
                # Фильтрация артефактов частиц
                if lemma in {'нибыть', 'либыть', 'тобыть', 'кое'} or lemma in russian_stopwords:
                    continue
                
                # Только знаменательные части речи
                if pos in {'NOUN', 'VERB', 'INFN', 'ADJF', 'ADJS', 'PRTF', 'PRTS'}:
                    lemmas.append(lemma)
            
            # Построение биграмм ТОЛЬКО внутри предложения
            for i in range(len(lemmas) - 1):
                a, b = lemmas[i], lemmas[i + 1]
                if a != b and len(a) >= 4 and len(b) >= 4:
                    colloc_dict[a].add(b)
                    colloc_dict[b].add(a)
        
        return dict(colloc_dict)


class LexiconEditor(QMainWindow):
    """Основное окно приложения — словарь словосочетаний"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Лабораторная №1 — Словарь словосочетаний (Вариант 7, Задание 3)")
        self.resize(1000, 650)
        self.lexicon = {}  # {lemma: set(partners)}
        self.init_ui()
        self.create_menu()
    
    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        
        # Панель управления
        btn_layout = QHBoxLayout()
        self.btn_load = QPushButton("Загрузить TXT/RTF")
        self.btn_save = QPushButton("Сохранить словарь (JSON)")
        self.btn_document = QPushButton("Документировать (отчёт)")
        self.btn_clear = QPushButton("Очистить всё")
        
        btn_layout.addWidget(self.btn_load)
        btn_layout.addWidget(self.btn_save)
        btn_layout.addWidget(self.btn_document)
        btn_layout.addWidget(self.btn_clear)
        layout.addLayout(btn_layout)
        
        # Поиск
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Поиск лексемы:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Введите часть лексемы для фильтрации...")
        self.search_input.textChanged.connect(self.filter_lexemes)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)
        
        # Основная панель: лексемы ←→ партнёры
        splitter = QSplitter(Qt.Horizontal)
        
        # Список лексем
        self.lexeme_list = QListWidget()
        self.lexeme_list.setMinimumWidth(250)
        self.lexeme_list.itemSelectionChanged.connect(self.show_partners)
        splitter.addWidget(self.lexeme_list)
        
        # Список партнёров
        partner_widget = QWidget()
        partner_layout = QVBoxLayout(partner_widget)
        partner_layout.addWidget(QLabel("Партнёры (словосочетания):"))
        self.partner_list = QListWidget()
        partner_layout.addWidget(self.partner_list)
        
        # Добавление/удаление партнёров
        edit_layout = QHBoxLayout()
        self.partner_input = QLineEdit()
        self.partner_input.setPlaceholderText("Новая лексема-партнёр (минимум 4 символа)")
        self.btn_add = QPushButton("Добавить")
        self.btn_remove = QPushButton("Удалить")
        
        edit_layout.addWidget(self.partner_input)
        edit_layout.addWidget(self.btn_add)
        edit_layout.addWidget(self.btn_remove)
        partner_layout.addLayout(edit_layout)
        
        splitter.addWidget(partner_widget)
        splitter.setSizes([350, 450])
        layout.addWidget(splitter)
        
        # Статусная строка
        self.statusBar().showMessage("Готов к работе. Загрузите текстовый файл (TXT/RTF).")
        
        # Обработчики кнопок
        self.btn_load.clicked.connect(self.load_file)
        self.btn_save.clicked.connect(self.save_lexicon)
        self.btn_document.clicked.connect(self.document_lexicon)
        self.btn_clear.clicked.connect(self.clear_all)
        self.btn_add.clicked.connect(self.add_partner)
        self.btn_remove.clicked.connect(self.remove_partner)
    
    def create_menu(self):
        """Создание меню помощи"""
        menubar = self.menuBar()
        help_menu = menubar.addMenu("Справка")
        
        # Краткая инструкция
        guide_action = QAction("Как работать со словарём", self)
        guide_action.triggered.connect(self.show_guide)
        help_menu.addAction(guide_action)
        
        # О программе
        about_action = QAction("О программе", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
    
    def load_file(self):
        """Загрузка и обработка текстового файла"""
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Открыть файл", "", "Текстовые файлы (*.txt *.rtf)"
        )
        if not filepath:
            return
        
        try:
            text = TextProcessor.read_file(filepath)
            if not text.strip():
                raise ValueError("Файл пустой или содержит только пробельные символы")
            
            new_collocs = TextProcessor.extract_collocations(text)
            
            # Объединение с существующим словарём
            for lemma, partners in new_collocs.items():
                if lemma not in self.lexicon:
                    self.lexicon[lemma] = set()
                self.lexicon[lemma].update(partners)
            
            self.update_lexeme_list()
            total_new = len([l for l in new_collocs if l not in self.lexicon or len(self.lexicon[l]) > 0])
            self.statusBar().showMessage(
                f"Файл '{os.path.basename(filepath)}' обработан: {len(new_collocs)} лексем, {sum(len(v) for v in new_collocs.values())//2} связей"
            )
            QMessageBox.information(
                self, "Успех", 
                f"Текст успешно обработан!\nДобавлено лексем: {len(new_collocs)}\nДобавлено связей: {sum(len(v) for v in new_collocs.values())//2}"
            )
        except Exception as e:
            QMessageBox.critical(self, "Ошибка обработки", f"Не удалось обработать файл:\n{str(e)}")
            self.statusBar().showMessage(f"Ошибка: {str(e)}")
    
    def update_lexeme_list(self):
        """Обновление списка лексем с учётом поиска"""
        self.lexeme_list.clear()
        search_text = self.search_input.text().lower().strip()
        
        lemmas = sorted(self.lexicon.keys())
        if search_text:
            lemmas = [l for l in lemmas if search_text in l.lower()]
        
        for lemma in lemmas:
            partners_count = len(self.lexicon[lemma])
            self.lexeme_list.addItem(f"{lemma} ({partners_count} партнёров)")
    
    def filter_lexemes(self):
        """Фильтрация при изменении поиска"""
        self.update_lexeme_list()
    
    def show_partners(self):
        """Отображение партнёров выбранной лексемы"""
        self.partner_list.clear()
        items = self.lexeme_list.selectedItems()
        if not items:
            return
        
        lemma = items[0].text().split(' (')[0]
        for partner in sorted(self.lexicon.get(lemma, [])):
            self.partner_list.addItem(partner)
    
    def add_partner(self):
        """Добавление новой связи"""
        items = self.lexeme_list.selectedItems()
        if not items:
            QMessageBox.warning(self, "Внимание", "Сначала выберите лексему в левом списке.")
            return
        
        lemma = items[0].text().split(' (')[0]
        partner_text = self.partner_input.text().strip().lower()
        if not partner_text or len(partner_text) < 4:
            QMessageBox.warning(self, "Внимание", "Партнёр должен содержать минимум 4 символа.")
            return
        
        # Лемматизация введённого слова
        parses = morph.parse(partner_text)
        if not parses:
            QMessageBox.warning(self, "Ошибка", f"Не удалось распознать слово '{partner_text}'")
            return
        
        partner_lemma = max(parses, key=lambda p: p.score).normal_form.lower()
        
        # Проверка на стоп-слова и артефакты
        if partner_lemma in russian_stopwords or partner_lemma in {'нибыть', 'либыть', 'тобыть'}:
            QMessageBox.warning(self, "Внимание", f"Лексема '{partner_lemma}' является служебной и не может быть партнёром.")
            return
        
        if lemma == partner_lemma:
            QMessageBox.warning(self, "Внимание", "Лексема не может быть партнёром самой себе.")
            return
        
        # Добавление двунаправленной связи
        if partner_lemma not in self.lexicon:
            self.lexicon[partner_lemma] = set()
        self.lexicon[lemma].add(partner_lemma)
        self.lexicon[partner_lemma].add(lemma)
        
        self.partner_input.clear()
        self.show_partners()
        self.update_lexeme_list()
        self.statusBar().showMessage(f"Добавлена связь: '{lemma}' ↔ '{partner_lemma}'")
    
    def remove_partner(self):
        """Удаление связи"""
        lemma_item = self.lexeme_list.selectedItems()
        partner_item = self.partner_list.selectedItems()
        if not lemma_item or not partner_item:
            QMessageBox.warning(self, "Внимание", "Выберите лексему слева и её партнёра справа для удаления.")
            return
        
        lemma = lemma_item[0].text().split(' (')[0]
        partner = partner_item[0].text()
        
        self.lexicon[lemma].discard(partner)
        self.lexicon[partner].discard(lemma)
        
        # Удаление пустых записей
        if lemma in self.lexicon and not self.lexicon[lemma]:
            del self.lexicon[lemma]
        if partner in self.lexicon and not self.lexicon[partner]:
            del self.lexicon[partner]
        
        self.update_lexeme_list()
        self.show_partners()
        self.statusBar().showMessage(f"Связь удалена: '{lemma}' ↔ '{partner}'")
    
    def save_lexicon(self):
        """Сохранение словаря в JSON"""
        if not self.lexicon:
            QMessageBox.warning(self, "Внимание", "Словарь пуст. Сначала загрузите текст.")
            return
        
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Сохранить словарь", "словарь_словосочетаний.json", "JSON файлы (*.json)"
        )
        if not filepath:
            return
        
        # Преобразование set → list для JSON
        serializable = {k: sorted(list(v)) for k, v in self.lexicon.items()}
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(serializable, f, ensure_ascii=False, indent=2)
        
        QMessageBox.information(self, "Сохранено", f"Словарь сохранён в:\n{filepath}")
        self.statusBar().showMessage(f"Словарь сохранён: {filepath}")
    
    def document_lexicon(self):
        """Генерация подробного текстового отчёта"""
        if not self.lexicon:
            QMessageBox.warning(self, "Внимание", "Словарь пуст. Сначала загрузите текст.")
            return
        
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Сохранить отчёт", "отчёт_словосочетания.txt", "Текстовые файлы (*.txt)"
        )
        if not filepath:
            return
        
        # Формирование отчёта
        report = "ДОКУМЕНТИРОВАННЫЙ СЛОВАРЬ СЛОВОСОЧЕТАНИЙ\n"
        report += "=" * 70 + "\n"
        report += f"Всего лексем: {len(self.lexicon)}\n"
        report += f"Всего уникальных связей: {sum(len(v) for v in self.lexicon.values()) // 2}\n"
        report += "=" * 70 + "\n\n"
        report += "Примечание: Словосочетания извлекаются ТОЛЬКО в пределах одного предложения.\n"
        report += "Лексемы — нормальные формы слов (например, 'книги' → 'книга').\n\n"
        report += "=" * 70 + "\n\n"
        
        for i, lemma in enumerate(sorted(self.lexicon.keys()), 1):
            partners = sorted(self.lexicon[lemma])
            report += f"{i}. ЛЕКСЕМА: «{lemma}»\n"
            report += f"   Партнёры ({len(partners)}): {', '.join(f'«{p}»' for p in partners)}\n\n"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report)
        
        QMessageBox.information(self, "Отчёт создан", f"Документированный отчёт сохранён:\n{filepath}")
        self.statusBar().showMessage(f"Отчёт сохранён: {filepath}")
    
    def clear_all(self):
        """Полная очистка словаря"""
        if not self.lexicon:
            QMessageBox.information(self, "Информация", "Словарь уже пуст.")
            return
        
        reply = QMessageBox.question(
            self, "Подтверждение", 
            "Очистить весь словарь? Все данные будут безвозвратно потеряны.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.lexicon.clear()
            self.lexeme_list.clear()
            self.partner_list.clear()
            self.search_input.clear()
            self.statusBar().showMessage("Словарь полностью очищен.")
    
    def show_guide(self):
        """Подробная инструкция пользователя"""
        guide = (
            "<h3>Руководство пользователя: Словарь словосочетаний</h3>"
            
            "<p><b>1. Загрузка текста</b><br>"
            "— Нажмите «Загрузить TXT/RTF» и выберите файл.<br>"
            "— Программа автоматически:<br>"
            "&nbsp;&nbsp;• разобьёт текст на предложения,<br>"
            "&nbsp;&nbsp;• извлечёт лексемы (нормальные формы),<br>"
            "&nbsp;&nbsp;• построит словосочетания ТОЛЬКО внутри предложений,<br>"
            "&nbsp;&nbsp;• отфильтрует служебные слова и артефакты.</p>"
            
            "<p><b>2. Просмотр связей</b><br>"
            "— Выберите лексему в левом списке.<br>"
            "— В правом списке отобразятся все лексемы, с которыми она образует словосочетания.<br>"
            "— Связи двунаправленные: если А сочетается с Б, то Б сочетается с А.</p>"
            
            "<p><b>3. Редактирование</b><br>"
            "— <u>Добавить связь</u>: выберите лексему → введите партнёра (мин. 4 символа) → «Добавить».<br>"
            "— <u>Удалить связь</u>: выделите партнёра в правом списке → «Удалить».<br>"
            "— Программа автоматически обновит обе стороны связи.</p>"
            
            "<p><b>4. Поиск и фильтрация</b><br>"
            "— Введите текст в поле «Поиск лексемы» — список отфильтруется в реальном времени.<br>"
            "— Поиск нечувствителен к регистру.</p>"
            
            "<p><b>5. Сохранение и документирование</b><br>"
            "— «Сохранить словарь» — экспорт в JSON для программной обработки.<br>"
            "— «Документировать» — создание читаемого отчёта в TXT с пояснениями.<br>"
            "— Оба формата поддерживают кириллицу без искажений.</p>"
            
            "<p><b>Важно:</b><br>"
            "• Словосочетания строятся ТОЛЬКО в пределах одного предложения (границы предложений строго соблюдаются).<br>"
            "• Обрабатываются только знаменательные части речи (существительные, глаголы, прилагательные).<br>"
            "• Служебные слова (предлоги, союзы, частицы) автоматически исключаются.<br>"
            "• Все формы слова приводятся к лексеме: «книги», «книге», «книгу» → «книга».</p>"
        )
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Инструкция")
        dialog.setText(guide)
        dialog.exec_()
    
    def show_about(self):
        """Информация о соответствии требованиям"""
        about = (
            "<h3>Словарь словосочетаний — Лабораторная работа №1</h3>"
            "<p><b>Вариант задания:</b> №7 (русский язык, форматы TXT/RTF, Задание 3)</p>"
            
            "<p><b>Реализованные функции:</b></p>"
            "<ul>"
            "<li>✅ Автоматическое построение словаря из текста</li>"
            "<li>✅ Корректная обработка границ предложений (устранены межпредложные связи)</li>"
            "<li>✅ Фильтрация служебных слов и артефактов (включая «нибыть»)</li>"
            "<li>✅ Сохранение в JSON</li>"
            "<li>✅ Просмотр в двухпанельном интерфейсе</li>"
            "<li>✅ Редактирование (добавление/удаление связей)</li>"
            "<li>✅ Ручное пополнение словаря</li>"
            "<li>✅ Фильтрация и поиск</li>"
            "<li>✅ Документирование с пояснениями</li>"
            "<li>✅ Система помощи (инструкция и информация)</li>"
            "</ul>"
            
            "<p><b>Ключевые улучшения по сравнению с базовой версией:</b></p>"
            "<ul>"
            "<li>✓ Разбиение текста на предложения через NLTK (sent_tokenize)</li>"
            "<li>✓ Сохранение дефисных слов при токенизации</li>"
            "<li>✓ Расширенная фильтрация стоп-слов и артефактов частиц</li>"
            "<li>✓ Учёт только знаменательных частей речи (NOUN, VERB, ADJF и др.)</li>"
            "<li>✓ Минимальная длина лексемы — 4 символа</li>"
            "</ul>"
            
            "<p><b>Используемые технологии:</b><br>"
            "Python 3.8+, PyQt5, NLTK (punkt, stopwords), PyMorphy3, striprtf</p>"
            
            "<p><b>Соответствие требованиям задания:</b><br>"
            "Полностью соответствует варианту №7: русский язык, форматы TXT/RTF,<br>"
            "Задание 3 — словарь лексем со словосочетаниями.</p>"
        )
        QMessageBox.about(self, "О программе", about)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    # Установка стиля для лучшей читаемости
    app.setStyle('Fusion')
    window = LexiconEditor()
    window.show()
    sys.exit(app.exec_())