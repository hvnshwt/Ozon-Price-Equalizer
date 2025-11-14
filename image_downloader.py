import requests

from PyQt5.QtGui import QPixmap
from PyQt5 import QtCore

from worker_signals import WorkerSignals

class ImageDownloader:
    """
    Класс-загрузчик изображений. Выполняется в отдельном потоке.
    """
    def __init__(self, urls: list, signals: WorkerSignals):
        self.urls = urls
        self.signals = signals

    def run(self):
        """
        Основной метод, который выполняет загрузку.
        """
        for i, url in enumerate(self.urls):
            try:
                # Выполняем запрос на получение изображения
                response = requests.get(url, stream=True)
                response.raise_for_status()  # Проверяем, что запрос успешен (код 2xx)

                pixmap = QPixmap()
                pixmap.loadFromData(response.content)
                thumbnail = pixmap.scaled(65, 65, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)

                # Отправляем сигнал о готовности изображения
                self.signals.image_ready.emit(i, thumbnail)

            except requests.exceptions.RequestException as e:
                print(f"Сетевая ошибка при загрузке {url}: {e}")
                self.signals.image_ready.emit(i, QPixmap()) # Отправляем пустой pixmap в случае ошибки
            except Exception as e:
                print(f"Неизвестная ошибка при обработке {url}: {e}")
                self.signals.image_ready.emit(i, QPixmap())

        # После завершения цикла отправляем сигнал о завершении всей работы
        self.signals.finished.emit()