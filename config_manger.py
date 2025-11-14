from PyQt5.QtCore import QSettings

class ConfigManager:
    """
    Класс для управления сохранением и загрузкой настроек приложения.
    Использует QSettings для кросс-платформенного хранения.
    """
    def __init__(self, organization_name="MyCompany", app_name="OzonStabilizer"):
        # Инициализируем QSettings. Эти имена определят, где будут храниться настройки.
        self.settings = QSettings(organization_name, app_name)

    def save_credentials(self, client_id, api_key):
        """Сохраняет учетные данные API."""
        print("Сохранение учетных данных...")
        self.settings.setValue("credentials/client_id", client_id)
        self.settings.setValue("credentials/api_key", api_key)

    def load_credentials(self):
        """Загружает учетные данные API."""
        print("Загрузка учетных данных...")
        client_id = self.settings.value("credentials/client_id", "") # Второй аргумент - значение по умолчанию
        api_key = self.settings.value("credentials/api_key", "")
        return client_id, api_key

    def save_tracked_products(self, client_id, products_dict):
        """Сохраняет словарь отслеживаемых товаров для КОНКРЕТНОГО магазина."""
        if not client_id: # Не сохраняем, если Client ID пустой
            return
        print(f"Сохранение отслеживаемых товаров для магазина {client_id}...")
        # Используем beginGroup для создания "папки" для каждого магазина
        self.settings.beginGroup(client_id)
        self.settings.setValue("tracked_products", products_dict)
        self.settings.endGroup()

    def load_tracked_products(self, client_id):
        """Загружает словарь отслеживаемых товаров для КОНКРЕТНОГО магазина."""
        if not client_id:
            return {}
        print(f"Загрузка отслеживаемых товаров для магазина {client_id}...")
        self.settings.beginGroup(client_id)
        tracked = self.settings.value("tracked_products", {}, type=dict)
        self.settings.endGroup()
        return tracked

    def save_coefficient(self, coefficient):
        """Сохраняет коэффициент скидки."""
        print(f"Сохранение коэффициента: {coefficient}")
        # Сохраняем значение. QSettings сам справится с типом float/double.
        self.settings.setValue("app/price_discount_coefficient", coefficient)

    def load_coefficient(self):
        """Загружает коэффициент скидки."""
        print("Загрузка коэффициента...")
        # Загружаем значение. Указываем значение по умолчанию (0.852) и тип float
        # на случай, если это первый запуск и в конфиге еще ничего нет.
        default_value = 0.852
        coefficient = self.settings.value("app/price_discount_coefficient", default_value, type=float)
        return coefficient

    def save_window_state(self, main_window):
        """Сохраняет размер и положение окна."""
        self.settings.setValue("window/geometry", main_window.saveGeometry())
        self.settings.setValue("window/state", main_window.saveState())

    def load_window_state(self, main_window):
        """Восстанавливает размер и положение окна."""
        geometry = self.settings.value("window/geometry")
        state = self.settings.value("window/state")
        if geometry:
            main_window.restoreGeometry(geometry)
        if state:
            main_window.restoreState(state)