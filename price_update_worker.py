from PyQt5 import QtCore

class PriceUpdateWorkerSignals(QtCore.QObject):
    """Сигналы для воркера обновления цен."""
    finished = QtCore.pyqtSignal(list)  # Завершено успешно, передает новый список продуктов
    error = QtCore.pyqtSignal(str)      # Произошла ошибка

class PriceUpdateWorker:
    """Воркер для фонового обновления цен через API."""
    def __init__(self, api_client):
        self.api_client = api_client
        self.signals = PriceUpdateWorkerSignals()

    def run(self):
        """Выполняет запрос к API и отправляет сигнал о завершении."""
        try:
            print("Фоновое обновление: запрашиваю новые данные о товарах...")
            # Эта функция может занять время, поэтому она в потоке
            new_products_list = self.api_client.get_products_with_details()
            new_products_list.reverse()
            self.signals.finished.emit(new_products_list)
        except Exception as e:
            error_message = f"Ошибка фонового обновления: {e}"
            print(error_message)
            self.signals.error.emit(error_message)
