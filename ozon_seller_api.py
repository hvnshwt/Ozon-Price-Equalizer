import requests
import json
from typing import List, Dict, Optional


class OzonSellerAPI:
    """
    Класс для взаимодействия с Ozon Seller API.
    """

    BASE_URL = "https://api-seller.ozon.ru"

    def __init__(self, client_id: str, api_key: str):
        """
        Инициализирует клиент API.

        Args:
            client_id: Ваш Client ID для доступа к API.
            api_key: Ваш API Key для доступа к API.
        """
        if not client_id or not api_key:
            raise ValueError("Client ID и Api-Key не могут быть пустыми.")

        self.client_id = client_id
        self.api_key = api_key
        self._headers = {
            "Client-Id": self.client_id,
            "Api-Key": self.api_key,
            "Content-Type": "application/json"
        }

    def _make_request(self, method: str, endpoint: str, payload: Optional[Dict] = None) -> Optional[Dict]:
        """
        Приватный метод для выполнения запросов к API.

        Args:
            method: HTTP-метод ('POST', 'GET').
            endpoint: Эндпоинт API (например, '/v3/product/list').
            payload: Тело запроса в виде словаря.

        Returns:
            Ответ от API в виде словаря или None в случае ошибки.
        """
        url = f"{self.BASE_URL}{endpoint}"
        try:
            if method.upper() == 'POST':
                response = requests.post(url, headers=self._headers, data=json.dumps(payload))
            else:  # Добавим GET для будущих методов
                response = requests.get(url, headers=self._headers, params=payload)

            response.raise_for_status()  # Проверка на ошибки HTTP (4xx/5xx)
            return response.json()

        except requests.exceptions.RequestException as e:
            print(f"Ошибка при запросе к API: {e}")
            if 'response' in locals() and response.text:
                print(f"Тело ответа: {response.text}")
            return None

    def get_product_list(self, limit: int = 1000, visibility: str = "ALL") -> List[Dict]:
        """
        Получает полный список товаров продавца, обрабатывая постраничную загрузку.

        Args:
            limit: Количество товаров на одной странице (максимум 1000).
            visibility: Фильтр по видимости товаров (ALL, VISIBLE, INVISIBLE и др.).

        Returns:
            Список словарей, где каждый словарь представляет один товар.
            В случае ошибки возвращает пустой список.
        """
        all_products = []
        last_id = ""

        print("Начинаю загрузку списка товаров...")
        while True:
            payload = {
                "filter": {
                    "visibility": visibility
                },
                "last_id": last_id,
                "limit": limit
            }

            data = self._make_request('POST', '/v3/product/list', payload)

            if not data:
                break  # Прерываем цикл при ошибке в _make_request

            result = data.get('result', {})
            products_on_page = result.get('items', [])

            if not products_on_page:
                break

            all_products.extend(products_on_page)
            print(f"Загружено {len(products_on_page)} товаров. Всего: {len(all_products)}")

            last_id = result.get('last_id', "")
            if not last_id:
                break

        print("Загрузка списка товаров завершена.")
        return all_products

    # --- ЗАГЛУШКИ ДЛЯ БУДУЩИХ МЕТОДОВ ---

    def get_product_info(self, product_ids: List[int] = None, offer_ids: List[str] = None, skus: List[int] = None) -> \
            List[Dict]:
        """
        Получает подробную информацию о товарах по их идентификаторам.
        Автоматически разбивает запрос на части по 1000 товаров.

        Args:
            product_ids: Список ID товаров (product_id).
            offer_ids: Список артикулов (offer_id).
            skus: Список SKU Ozon.

        Returns:
            Список словарей с детальной информацией о каждом товаре.
        """
        if not any([product_ids, offer_ids, skus]):
            print("Необходимо передать хотя бы один список идентификаторов (product_ids, offer_ids или skus).")
            return []

        # Определяем, какой идентификатор использовать
        if product_ids:
            id_list, id_key = product_ids, "product_id"
        elif offer_ids:
            id_list, id_key = offer_ids, "offer_id"
        else:
            id_list, id_key = skus, "sku"

        all_details = []
        chunk_size = 1000
        print(f"Шаг 2: Начинаю загрузку детальной информации для {len(id_list)} товаров...")

        for i in range(0, len(id_list), chunk_size):
            chunk = id_list[i:i + chunk_size]
            payload = {id_key: chunk}

            data = self._make_request('POST', '/v3/product/info/list', payload)

            if data and 'items' in data:
                all_details.extend(data['items'])
                print(f"  - Загружены детали для {len(all_details)}/{len(id_list)} товаров...")

        print("Шаг 2: Загрузка деталей завершена.")
        return all_details

    def get_products_with_details(self) -> List[Dict]:
        """
        Высокоуровневый метод: получает полный список товаров со всей необходимой информацией.
        Объединяет данные из get_product_list() и get_product_info().

        Returns:
            Полный список товаров с детальной информацией.
        """
        # Шаг 1: Получаем базовый список
        product_list = self.get_product_list()
        if not product_list:
            return []

        # Шаг 2: Извлекаем product_id для следующего запроса
        product_ids = [p['product_id'] for p in product_list]

        # Шаг 3: Получаем детальную информацию
        product_details = self.get_product_info(product_ids=product_ids)
        if not product_details:
            return product_list  # Возвращаем хотя бы базовый список, если детали не загрузились

        # Шаг 4: Объединяем информацию для удобного доступа
        details_map = {item['id']: item for item in product_details}

        enriched_products = []
        for product in product_list:
            details = details_map.get(product['product_id'])
            if details:
                product.update(details)  # Добавляем всю детальную информацию к базовой
            enriched_products.append(product)

        return enriched_products

    def update_prices(self, price_data: List[Dict]) -> Dict[str, List]:
        """
        Обновляет цены для списка товаров.

        Args:
            price_data: Список словарей, каждый из которых содержит данные для обновления.
                        Пример:
                        [
                            {
                                "product_id": 12345,
                                "price": "1599.00",
                                "old_price": "1999.00",
                                "currency_code": "RUB"
                            },
                            {
                                "offer_id": "ART-002",
                                "price": "999.50"
                            }
                        ]
                        Обязательные поля: (product_id или offer_id) и price.

        Returns:
            Словарь с результатами обновления: {'successful': [...], 'failed': [...]}.
        """
        if not isinstance(price_data, list) or not price_data:
            print("Ошибка: price_data должен быть непустым списком словарей.")
            return {"successful": [], "failed": []}

        print(f"Начинаю обновление цен для {len(price_data)} позиций...")

        successful_updates = []
        failed_updates = []
        chunk_size = 1000

        for i in range(0, len(price_data), chunk_size):
            chunk = price_data[i:i + chunk_size]
            payload = {"prices": chunk}

            response_data = self._make_request('POST', '/v1/product/import/prices', payload)

            if response_data and 'result' in response_data:
                results = response_data['result']
                for res in results:
                    if res.get('updated'):
                        successful_updates.append(res)
                    else:
                        failed_updates.append(res)
                print(f"  - Обработана пачка из {len(chunk)} товаров.")
            else:
                # Если весь запрос не удался, отмечаем все товары в чанке как неудачные
                print(f"  - Ошибка при обработке пачки из {len(chunk)} товаров.")
                failed_updates.extend(chunk)

        print("Обновление цен завершено.")
        return {"successful": successful_updates, "failed": failed_updates}
