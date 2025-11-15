import json
import sys
import os
import threading
from functools import partial
import math

from ozon_seller_api import OzonSellerAPI
from worker_signals import WorkerSignals
from image_downloader import ImageDownloader
from price_update_worker import PriceUpdateWorker, PriceUpdateWorkerSignals
from config_manger import ConfigManager

from PyQt5 import QtCore, QtWidgets, QtGui, Qt
from PyQt5.QtCore import QIODevice, QTimer
# from PyQt5.QtWidgets import QTableWidgetSelectionRange, QMessageBox, QFileDialog, QStyle
from PyQt5.QtWidgets import QWidget, QCheckBox, QHBoxLayout, QTableWidget, QApplication, QTableWidgetItem

import window

os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"

def resource_path(relative_path):
    """ Получаем абсолютный путь к ресурсу, работает для dev и для PyInstaller """
    try:
        # PyInstaller создает временную папку и сохраняет путь в _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class Window(QtWidgets.QMainWindow, window.Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        icon_path = resource_path("ozon_logo.ico")
        self.setWindowIcon(QtGui.QIcon(icon_path))

        self.api_client = None
        self.price_worker = None
        self.start_btn.clicked.connect(self.start)
        self.detailed_products = None
        self.tableWidget.setColumnWidth(0, 65)
        self.tracked_products = {}
        self.is_update_running = False
        self.is_running = False
        self.price_discount_coef = 0.852
        self.config_manager = ConfigManager()

        self.coef_spin_box.setValue(self.price_discount_coef)
        self.coef_spin_box.setEnabled(False)

        # 1. Создаем таймер
        self.price_update_timer = QTimer(self)
        # Устанавливаем интервал в миллисекундах (10 минут * 60 секунд * 1000 мс)
        self.price_update_timer.setInterval(60000)  # поставить 300000 (5 минут)
        # Подключаем сигнал таймера к слоту-запускатору
        self.price_update_timer.timeout.connect(self.start_price_update)

        # Флаг для отслеживания состояния фильтра
        self.is_status_filtered = False
        # Константа для удобства, чтобы не использовать "магическое число" 3
        self.STATUS_COLUMN_INDEX = 3
        # Подключаем сигнал клика по заголовку
        self.tableWidget.horizontalHeader().sectionClicked.connect(self.on_header_clicked)

        # 1. Флаг для режима редактирования
        self.is_edit_mode = False
        # 2. Список для хранения ссылок на виджеты в таблице
        self.table_widgets = []
        # 3. Подключаем кнопку редактирования к новому методу
        self.edit_btn.clicked.connect(self.toggle_edit_mode)
        self.select_all_btn.clicked.connect(self.select_all_or_none)

        self.load_settings()

    def load_settings(self):
        """Загружает ОБЩИЕ настройки."""
        print("Загрузка общих настроек...")
        client_id, api_key = self.config_manager.load_credentials()
        self.client_ID_lineEdit.setText(client_id)
        self.API_key_lineEdit.setText(api_key)

        # Загружаем коэффициент
        self.price_discount_coef = self.config_manager.load_coefficient()
        self.coef_spin_box.setValue(self.price_discount_coef)

        # Восстанавливаем состояние окна
        self.config_manager.load_window_state(self)

    def save_settings(self):
        """Сохраняет ВСЕ настройки при выходе."""
        print("Сохранение настроек приложения...")
        current_client_id = self.client_ID_lineEdit.text()

        # Сохраняем общие настройки
        self.config_manager.save_credentials(
            current_client_id,
            self.API_key_lineEdit.text()
        )
        self.config_manager.save_coefficient(self.coef_spin_box.value())
        self.config_manager.save_window_state(self)

        # Сохраняем данные ТЕКУЩЕГО магазина
        self.config_manager.save_tracked_products(current_client_id, self.tracked_products)

    def closeEvent(self, event):
        """
        Этот метод автоматически вызывается, когда пользователь закрывает окно.
        Идеальное место для сохранения настроек.
        """
        self.save_settings()
        event.accept()  # Подтверждаем закрытие

    def start(self):
        if not self.is_running:
            self.tableWidget.clearContents()
            MY_CLIENT_ID = self.client_ID_lineEdit.text()
            MY_API_KEY = self.API_key_lineEdit.text()

            self.tracked_products = self.config_manager.load_tracked_products(MY_CLIENT_ID)
            print(f"Загружены настройки отслеживания для магазина {MY_CLIENT_ID}")

            self.client_ID_lineEdit.setEnabled(False)
            self.API_key_lineEdit.setEnabled(False)
            self.start_btn.setText("Остановить")

            self.api_client = OzonSellerAPI(client_id=MY_CLIENT_ID, api_key=MY_API_KEY)

            self.detailed_products = self.api_client.get_products_with_details()
            self.detailed_products.reverse()
            self.make_table(self.detailed_products)
            print("Запускаю первичное обновление цен...")
            self.start_price_update()

            self.is_running = True
        else:
            self.client_ID_lineEdit.setEnabled(True)
            self.API_key_lineEdit.setEnabled(True)
            self.start_btn.setText("Начать")
            self.price_update_timer.stop()
            print("Таймер фонового обновления остановлен.")
            self.is_running = False

    def start_price_update(self):
        """Слот, который запускает фоновый процесс обновления цен."""
        if self.api_client is None:
            return  # Не запускаем, если API не инициализирован

        print("Начинаю обновление... Таймер остановлен на время работы.")
        self.is_update_running = True  # 1. Устанавливаем флаг-блокировку
        self.price_update_timer.stop()  # 2. Останавливаем таймер

        # 1. Создаем воркера
        self.price_worker = PriceUpdateWorker(api_client=self.api_client)

        # 2. Подключаем его сигналы к методам-обработчикам
        self.price_worker.signals.finished.connect(self.handle_price_update)
        self.price_worker.signals.error.connect(self.handle_price_error)

        # 3. Создаем и запускаем поток
        thread = threading.Thread(target=self.price_worker.run)
        thread.daemon = True
        thread.start()

    def handle_price_error(self, error_message):
        """Обрабатывает ошибку от фонового воркера."""
        # Здесь можно показать уведомление пользователю
        print(f"Не удалось обновить цены: {error_message}")
        self.is_update_running = False  # 1. Снимаем блокировку
        self.price_update_timer.start()  # 2. Перезапускаем таймер для следующей попытки
        print(f"Следующая попытка обновления через {self.price_update_timer.interval() / 60000} минут.")

    def handle_price_update(self, new_products_list):
        """
        Основной метод, который обрабатывает новые данные, сравнивает цены
        и обновляет таблицу.
        """
        try:
            print("Фоновое обновление: получены новые данные. Сравниваю цены...")

            # 1. Создаем словарь старых цен для отслеживаемых товаров для быстрой проверки
            old_tracked_prices = {}
            for offer_id in self.tracked_products.keys():
                # Находим старые данные для товара
                product_data = self.tracked_products.get(offer_id, {})
                old_tracked_prices[offer_id] = product_data

            # 2. Обновляем наш основной источник данных
            self.detailed_products = new_products_list

            # 3. Обновляем всю таблицу новыми данными
            for row in range(self.tableWidget.rowCount()):
                # Получаем offer_id из ячейки, чтобы найти новые данные
                offer_id_item = self.tableWidget.item(row, 1)
                if not offer_id_item:
                    continue

                offer_id = offer_id_item.text()

                # Находим новые данные для этого offer_id
                new_data = next((p for p in new_products_list if p.get('offer_id') == offer_id), None)
                if new_data:
                    # Обновляем ячейку с ценой в таблице
                    new_price = new_data.get('price', 'Цена не найдена')
                    marketing_price = new_data.get('marketing_price', 'Цена не найдена')
                    
                    try:
                        new_price = float(new_price)
                    except ValueError as e:
                        continue
                    try:
                        marketing_price = float(marketing_price)
                    except ValueError as e:
                        marketing_price = new_price

                    self.tableWidget.item(row, 4).setText(
                        str(math.ceil(float(new_price) * self.get_final_coef(float(new_price), float(marketing_price)))) + '.00'
                    )

            if self.is_edit_mode:
                return

            products_to_update = []

            current_product_prices = {}

            # 4. Сравниваем цены для отслеживаемых товаров
            for offer_id, old_price in old_tracked_prices.items():
                new_data = next((p for p in new_products_list if p.get('offer_id') == offer_id), None)
                if new_data:
                    
                    try:
                        new_price = float(new_data.get('price', 'Цена не найдена'))
                    except ValueError as e:
                        continue
                    try:
                        new_marketing_price = float(new_data.get('marketing_price', 'Цена не найдена'))
                    except ValueError as e:
                        new_marketing_price = new_price
                        
                    current_product_prices[offer_id] = [new_price, new_marketing_price]
                        
                    # Также обновляем данные в нашем словаре отслеживаемых товаров
                    # self.tracked_products[offer_id] = new_data

                    if new_price > self.tracked_products[offer_id] * 1.01 or new_price < self.tracked_products[offer_id] * 0.99:
                        print(f"!!! ИЗМЕНЕНИЕ ЦЕНЫ для {offer_id}: было '{old_price}', стало '{new_price}'")
                        products_to_update.append(offer_id)
            self.set_prices(products_to_update, self.tracked_products, current_product_prices)

            print("Фоновое обновление завершено.")
        finally:
            self.is_update_running = False  # 1. Снимаем блокировку
            self.price_update_timer.start()  # 2. Перезапускаем таймер
            print(f"Следующее обновление запланировано через {self.price_update_timer.interval() / 60000} минут.")

    def set_prices(self, products_to_update, tracked_products, current_product_prices):
        query_list = []
        for offer_id in products_to_update:
            price = current_product_prices[offer_id][0]
            marketing_price = current_product_prices[offer_id][1]
            query_list.append({
                "offer_id": offer_id,
                "price": str(math.ceil(float(tracked_products[offer_id] / self.get_final_coef(price, marketing_price)))) + '.00',  # Новая цена
                "old_price": "0",  # Новая зачеркнутая цена
                "currency_code": "RUB"
            })
        print(json.dumps(query_list, indent=2, ensure_ascii=False))
        update_results = self.api_client.update_prices(query_list)
        print("\n--- Результаты обновления ---")
        print(f"Успешно обновлено: {len(update_results['successful'])}")
        for success in update_results['successful']:
            print(f"  - Offer ID: {success.get('offer_id')}, Product ID: {success.get('product_id')}")

        if update_results['failed']:
            print(f"\nНе удалось обновить: {len(update_results['failed'])}")
            for failure in update_results['failed']:
                print(f"  - Offer ID: {failure.get('offer_id')}, Ошибки: {failure.get('errors')}")

        # self.start_price_update()

    def toggle_edit_mode(self):
        """Переключает режим редактирования и состояние виджетов."""
        was_in_edit_mode = self.is_edit_mode
        # Инвертируем флаг (True -> False, False -> True)
        self.is_edit_mode = not self.is_edit_mode

        # Обновляем текст на кнопке для наглядности
        self.edit_btn.setText("Применить" if self.is_edit_mode else "Редактировать")
        self.select_all_btn.setEnabled(self.is_edit_mode)
        self.coef_spin_box.setEnabled(self.is_edit_mode)

        # Проходимся по всем сохраненным виджетам
        for widgets in self.table_widgets:
            checkbox = widgets['checkbox']
            line_edit = widgets['line_edit']

            if was_in_edit_mode and not self.is_edit_mode:
                # ...и если чекбокс отмечен, а поле для ввода пустое...
                # .strip() удаляет пробелы по краям, чтобы поле из одних пробелов считалось пустым
                if checkbox.isChecked() and not line_edit.text().strip():
                    # ...то снимаем отметку.
                    # Это автоматически вызовет on_checkbox_state_changed,
                    # который уберет товар из отслеживания.
                    checkbox.setChecked(False)

            # Включаем или выключаем чекбоксы
            checkbox.setEnabled(self.is_edit_mode)

            is_line_edit_active = self.is_edit_mode and checkbox.isChecked()
            line_edit.setEnabled(is_line_edit_active)

            # Если мы выходим из режима редактирования, выключаем все LineEdit
            if not self.is_edit_mode:
                line_edit.setEnabled(False)
                self.price_discount_coef = self.coef_spin_box.value()
            # Если входим - LineEdit останется выключенным, пока не нажмут на его чекбокс
            # Это поведение управляется в on_checkbox_state_changed
        if was_in_edit_mode and not self.is_edit_mode:
            print("Отслеживаемые товары:", self.tracked_products)
            print("Запускаю немедленное обновление цен после редактирования...")
            # ...то запускаем обновление цен ОДИН РАЗ.
            self.start_price_update()

    def select_all_or_none(self):
        """
        Отмечает все чекбоксы, если хотя бы один не отмечен.
        Снимает все отметки, если все чекбоксы уже были отмечены.
        """
        # Проверка, что мы в режиме редактирования и таблица не пуста
        if not self.is_edit_mode or not self.table_widgets:
            return

        # Проверяем, все ли чекбоксы уже отмечены.
        # all() вернет True, только если все элементы True.
        all_are_checked = all(w['checkbox'].isChecked() for w in self.table_widgets)

        if not all_are_checked:
            self.select_all_btn.setText("Отменить всё")
        else:
            self.select_all_btn.setText("Выбрать всё")

        # Определяем новое состояние: если все были отмечены, новое состояние - False (снять),
        # в противном случае - True (отметить).
        new_state = not all_are_checked

        # Применяем новое состояние ко всем чекбоксам
        for widgets in self.table_widgets:
            # setChecked вызовет сигнал stateChanged, только если состояние реально изменится
            widgets['checkbox'].setChecked(new_state)

    def on_header_clicked(self, column_index):
        """
        Слот, который вызывается при клике на заголовок любого столбца.
        """
        # Проверяем, что клик был именно по столбцу "Статус"
        if column_index == self.STATUS_COLUMN_INDEX:
            # Инвертируем (переключаем) состояние фильтра
            self.is_status_filtered = not self.is_status_filtered

            # Вызываем функцию, которая применит фильтр к таблице
            self.apply_status_filter()

    def apply_status_filter(self):
        """
        Проходит по всем строкам таблицы и скрывает/показывает их
        в зависимости от состояния флага self.is_status_filtered.
        """
        if self.is_status_filtered:
            header_text = "Статус (Фильтр)"
        else:
            header_text = "Статус (Все)"

            # 2. Создаем новый элемент для заголовка с этим текстом
        status_header_item = QtWidgets.QTableWidgetItem(header_text)

        # 3. Устанавливаем этот новый элемент в качестве заголовка для нашего столбца
        self.tableWidget.setHorizontalHeaderItem(self.STATUS_COLUMN_INDEX, status_header_item)

        print(f"Применение фильтра. Текущее состояние: {'Включен' if self.is_status_filtered else 'Выключен'}")

        # Проходим по каждой строке таблицы
        for row in range(self.tableWidget.rowCount()):
            # Если фильтр включен
            if self.is_status_filtered:
                # Получаем ячейку со статусом из текущей строки
                status_item = self.tableWidget.item(row, self.STATUS_COLUMN_INDEX)

                # Проверяем, что ячейка существует и ее текст НЕ "Продается"
                if status_item and status_item.text() != 'Продается':
                    # Скрываем строку, которая не подходит под условие
                    self.tableWidget.setRowHidden(row, True)
                else:
                    # Показываем строку, которая подходит
                    self.tableWidget.setRowHidden(row, False)
            # Если фильтр выключен
            else:
                # Просто показываем все строки
                self.tableWidget.setRowHidden(row, False)

    def make_table(self, detailed_products):
        # Сбрасываем состояние фильтра при полной перезагрузке таблицы
        self.is_status_filtered = False
        self.apply_status_filter()  # Убирает скрытие со всех строк, если оно было

        self.table_widgets.clear()

        row_count = len(detailed_products)
        column_count = self.tableWidget.columnCount()
        self.tableWidget.setRowCount(row_count)

        urls = []

        if detailed_products:
            for i,  product in enumerate(detailed_products):
                # Безопасно извлекаем данные
                name = product.get('name', 'Название не найдено')
                price = product.get('price', 'Цена не найдена')
                marketing_price = product.get('marketing_price', 'Маркетинговая цена не найдена')
                
                # Обработка ошибок "Цена не найдена"
                try:
                    price = float(price)
                except ValueError as e:
                    continue
                try:
                    marketing_price = float(marketing_price)
                except ValueError as e:
                    marketing_price = price
                
                
                status = product.get('statuses', {}).get('status_description', 'Статус не найден')
                if status == '':
                    status = 'Продается'
                primary_image = product.get('primary_image', 'Главное фото не найдено')
                offer_id = product.get('offer_id', 'Артикул не найден')

                if len(primary_image) > 0:
                    urls.append(primary_image[0])

                checkBoxWidget = QWidget()
                checkBox = QCheckBox()
                checkBox.setEnabled(False)
                layoutCheckBox = QHBoxLayout(checkBoxWidget)
                layoutCheckBox.addWidget(checkBox)
                layoutCheckBox.setAlignment(QtCore.Qt.AlignCenter)
                layoutCheckBox.setContentsMargins(0, 0, 0, 0)

                lineEditWidget = QWidget()
                lineEdit = QtWidgets.QLineEdit()
                lineEdit.setEnabled(False)
                only_int_validator = QtGui.QIntValidator(0, 99999)
                lineEdit.setValidator(only_int_validator)
                lineEdit.editingFinished.connect(
                    partial(self.on_lineedit_editing_finished, offer_id, lineEdit)
                )
                layoutlineEdit = QHBoxLayout(lineEditWidget)
                layoutlineEdit.addWidget(lineEdit)
                layoutlineEdit.setAlignment(QtCore.Qt.AlignCenter)
                layoutlineEdit.setContentsMargins(0, 0, 0, 0)

                checkBox.stateChanged.connect(
                    partial(self.on_checkbox_state_changed, offer_id, lineEdit)
                )
                if offer_id in self.tracked_products:
                    # Если да, отмечаем чекбокс
                    checkBox.setChecked(True)
                    # И устанавливаем сохраненную желаемую цену в lineEdit
                    preferred_price = self.tracked_products.get(offer_id)
                    lineEdit.setText(str(preferred_price))

                self.table_widgets.append({
                    'checkbox': checkBox,
                    'line_edit': lineEdit
                })

                self.tableWidget.setItem(i, 0, QtWidgets.QTableWidgetItem("Загрузка..."))
                self.tableWidget.setItem(i, 1, QtWidgets.QTableWidgetItem(offer_id))
                self.tableWidget.setItem(i, 2, QtWidgets.QTableWidgetItem(name))
                self.tableWidget.setItem(i, 3, QtWidgets.QTableWidgetItem(status))
                self.tableWidget.setItem(i, 4, QtWidgets.QTableWidgetItem(
                    str(math.ceil(float(price) * self.get_final_coef(float(price), float(marketing_price)))) + '.00')
                )
                self.tableWidget.setCellWidget(i, 5, checkBoxWidget)
                self.tableWidget.setCellWidget(i, 6, lineEditWidget)
            self.start_download(urls)

    def get_final_coef(self, seller_price, market_price):
        coef = self.coef_spin_box.value()
        return (market_price / seller_price) * coef

    def on_checkbox_state_changed(self, offer_id, line_edit, state):
        """
        Этот метод вызывается при изменении состояния чекбокса.
        :param offer_id: Артикул товара.
        :param line_edit: Объект QLineEdit из той же строки.
        :param state: Состояние чекбокса (Checked или Unchecked).
        """
        if state == QtCore.Qt.Checked:
            print(f"Товар с артикулом {offer_id} добавлен в отслеживание.")
            preferred_price = None
            if line_edit.text() != '':
                preferred_price = int(line_edit.text())
            if preferred_price:
                self.tracked_products[offer_id] = preferred_price

            # ИЗМЕНЕНИЕ 3: Включаем lineEdit
            line_edit.setEnabled(True)
            line_edit.setPlaceholderText("Введите цену...")  # Полезный плейсхолдер

        else:
            print(f"Товар с артикулом {offer_id} убран из отслеживания.")
            if offer_id in self.tracked_products:
                del self.tracked_products[offer_id]

            # ИЗМЕНЕНИЕ 3: Выключаем и очищаем lineEdit
            line_edit.setEnabled(False)
            # line_edit.clear()  # Очищаем текст
            line_edit.setPlaceholderText("")  # Убираем плейсхолдер

        print("Отслеживаемые товары:", list(self.tracked_products.keys()))

    def on_lineedit_editing_finished(self, offer_id, line_edit):
        preferred_price = None
        if line_edit.text() != '':
            preferred_price = int(line_edit.text())
            line_edit.setText(str(preferred_price))
        if preferred_price:
            self.tracked_products[offer_id] = preferred_price
        print(f"Товару с артикулом {offer_id} присвоена желаемая цена: {preferred_price}.")

    def start_download(self, urls):
        """Запускает процесс загрузки в отдельном потоке."""
        # 1. Создаем объект с сигналами
        self.worker_signals = WorkerSignals()
        self.worker_signals.image_ready.connect(self.update_image_in_table)
        # self.worker_signals.finished.connect(self.on_download_finished)

        # 2. Создаем ЭКЗЕМПЛЯР нашего загрузчика
        downloader = ImageDownloader(
            urls=urls,
            signals=self.worker_signals
        )

        # 3. Создаем и запускаем поток, целью которого является метод `run` нашего объекта
        thread = threading.Thread(target=downloader.run)
        thread.daemon = True
        thread.start()

    def update_image_in_table(self, row, pixmap):
        """Слот для обновления ячейки с изображением. Выполняется в основном потоке."""
        self.tableWidget.setItem(row, 0, QtWidgets.QTableWidgetItem(""))
        if not pixmap.isNull():
            self.tableWidget.setRowHeight(row, 65)
            label = QtWidgets.QLabel()
            label.setPixmap(pixmap)  # Масштабируем для ячейки
            self.tableWidget.setCellWidget(row, 0, label)

        else:
            self.tableWidget.setItem(row, 0, QTableWidgetItem("Ошибка"))


def main():
    app = QtWidgets.QApplication(sys.argv)
    window_app = Window()
    window_app.show()
    app.exec_()


if __name__ == "__main__":
    main()
