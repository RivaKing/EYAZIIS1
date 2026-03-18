#!/bin/bash

# Автоматически определяем путь к текущей директории
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Ищем виртуальное окружение (папки venv, .venv, env, .env)
VENV_DIR=""
for venv_name in "venv" ".venv" "env" ".env"; do
    if [ -d "$SCRIPT_DIR/$venv_name" ]; then
        VENV_DIR="$SCRIPT_DIR/$venv_name"
        echo "Найдено виртуальное окружение: $VENV_DIR"
        break
    fi
done

# Проверяем, что виртуальное окружение найдено
if [ -z "$VENV_DIR" ]; then
    echo "Ошибка: Виртуальное окружение не найдено в $SCRIPT_DIR"
    echo "Искали папки: venv, .venv, env, .env"
    exit 1
fi

# Проверяем, что main.py существует
if [ ! -f "$SCRIPT_DIR/main.py" ]; then
    echo "Ошибка: main.py не найден в $SCRIPT_DIR"
    exit 1
fi

# Определяем путь к Python в виртуальном окружении
PYTHON_PATH="$VENV_DIR/bin/python"

# Проверяем, что Python существует
if [ ! -f "$PYTHON_PATH" ]; then
    echo "Ошибка: Python не найден в виртуальном окружении по пути $PYTHON_PATH"
    exit 1
fi

# Устанавливаем переменную окружения для Qt и запускаем приложение
echo "Запуск приложения с Wayland платформой..."
QT_QPA_PLATFORM=wayland "$PYTHON_PATH" "$SCRIPT_DIR/main.py"

# Если запуск с Wayland не удался, пробуем с xcb
if [ $? -ne 0 ]; then
    echo "Запуск с Wayland не удался, пробуем с xcb..."
    QT_QPA_PLATFORM=xcb "$PYTHON_PATH" "$SCRIPT_DIR/main.py"
fi