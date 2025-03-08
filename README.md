Преглед на кода и функционалностите
Този Flask-базиран уеб сървър управлява складова система с интеграция на RFID, OPC UA, управление на продукти и категории, както и контрол на светофари.

Основни модули и техните функции
Автентикация на потребители:

/login: Позволява на потребителите да влязат в системата.
/logout: Изчиства сесията на потребителя.
RFID интеграция:

/rfid/auth: Проверява валидността на RFID таговете спрямо базата данни.
Управление на продукти и категории:

/products: Създаване и управление на продукти.
/categories: Създаване и управление на категории.
Категоризиране на шкафове:

/cabinets: Позволява задаване на категории към шкафове.
Управление на светофари:

/traffic-light: Изпраща команди към OPC UA сървъра за контрол на светофарите (зелено, жълто, червено).
Зареждане и изтегляне на артикули с RFID:

/load: Добавя продукти в склада, само след проверка на RFID достъп.
/get: Изтегляне на продукти от склада, отново след RFID проверка.
Интеграция с OPC UA за управление на складовата автоматизация:

/opcua/update: Изпраща команди към OPC UA сървъра за управление на индустриални устройства.
Грешки и алармени съобщения:

/error: Логва грешки в системата и ги записва във warehouse_log.log.
Какво липсва или може да бъде подобрено?
✅ Добавяне на логове – В момента има логове за грешки, но може да се разшири с:

Логване на успешни и неуспешни операции.
История на зареждане и теглене на продукти.
✅ Реално време известия – Добавяне на WebSockets за нотификации в реално време.

✅ Подобряване на сигурността – Използване на хеширане на пароли и JWT за токени.

✅ История на операции – Проследяване на всички промени по продуктите (кой потребител е направил операцията, кога и какво е променил).

Следващи стъпки
a. Искате ли логове за всички действия на потребителите?
b. Нужно ли е известяване в реално време при грешки или липса на наличност?
