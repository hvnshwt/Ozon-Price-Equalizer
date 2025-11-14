from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtGui import QPixmap

class WorkerSignals(QObject):
    """
    Определяет сигналы для рабочего потока.
    - image_ready: передает номер строки (int) и загруженное изображение (QPixmap).
    - finished: сообщает о завершении всей работы.
    """
    image_ready = pyqtSignal(int, QPixmap)
    finished = pyqtSignal()